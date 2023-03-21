import openai
from termcolor import colored
import streamlit as st

from database import get_redis_connection,get_redis_results

from config import CHAT_MODEL,COMPLETIONS_MODEL, INDEX_NAME

redis_client = get_redis_connection()

# A basic class to create a message as a dict for chat
class Message:
    
    
    def __init__(self,role,content):
        
        self.role = role
        self.content = content
        
    def message(self):
        
        return {"role": self.role,"content": self.content}

# New Assistant class to add a vector database call to its responses
class RetrievalAssistant:
    
    def __init__(self):
        self.conversation_history = []  

    def _get_assistant_response(self, prompt):
        
        try:
            completion = openai.ChatCompletion.create(
              model=CHAT_MODEL,
              messages=prompt,
              temperature=0.1
            )
            
            response_message = Message(completion['choices'][0]['message']['role'],completion['choices'][0]['message']['content'])
            return response_message.message()
            
        except Exception as e:
            
            return f'Request failed with exception {e}'
    
    # The function to retrieve Redis search results
    def _get_search_results(self,prompt):
        latest_question = prompt
        search_content = get_redis_results(redis_client,latest_question,INDEX_NAME)['result'][0]
        return search_content
        

    def ask_assistant(self, next_user_prompt):
        [self.conversation_history.append(x) for x in next_user_prompt]
        assistant_response = self._get_assistant_response(self.conversation_history)
        
        # Answer normally unless the trigger sequence is used "searching_for_answers"
        if 'searching for answers' in assistant_response['content'].lower():
            question_extract = openai.Completion.create(model=COMPLETIONS_MODEL,prompt=f"Extract the user's latest question and the year for that question from this conversation: {self.conversation_history}. Extract it as a sentence stating the Question and Year")
            search_result = self._get_search_results(question_extract['choices'][0]['text'])
            
            # We insert an extra system prompt here to give fresh context to the Chatbot on how to use the Redis results
            # In this instance we add it to the conversation history, but in production it may be better to hide
            self.conversation_history.insert(-1,{"role": 'system',"content": f"Answer the user's question using this content: {search_result}. If you cannot answer the question, say 'Sorry, I don't know the answer to this one'"})
            
            assistant_response = self._get_assistant_response(self.conversation_history)
            
            self.conversation_history.append(assistant_response)
            return assistant_response
        else:
            self.conversation_history.append(assistant_response)
            return assistant_response
            
        
    def pretty_print_conversation_history(self, colorize_assistant_replies=True):
        for entry in self.conversation_history:
            if entry['role'] == 'system':
                pass
            else:
                prefix = entry['role']
                content = entry['content']
                output = colored(prefix +':\n' + content, 'green') if colorize_assistant_replies and entry['role'] == 'assistant' else prefix +':\n' + content
                #prefix = entry['role']
                print(output)