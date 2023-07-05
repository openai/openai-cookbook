const lancedb = require('vectordb')
const fs = require('fs/promises')
const readline = require('readline/promises')
const { stdin: input, stdout: output } = require('process')
const { Configuration, OpenAIApi } = require('openai')

// Download file from XYZ
const INPUT_FILE_NAME = 'youtube-transcriptions_sample.jsonl';

(async () => {
  // You need to provide an OpenAI API key, here we read it from the OPENAI_API_KEY environment variable
  const apiKey = process.env.OPENAI_API_KEY
  // The embedding function will create embeddings for the 'context' column
  const embedFunction = new lancedb.OpenAIEmbeddingFunction('context', apiKey)

  // Connects to LanceDB
  const db = await lancedb.connect('.tmp/youtube-lancedb')

  // Open the vectors table or create one if it does not exist
  let tbl
  if ((await db.tableNames()).includes('vectors')) {
    tbl = await db.openTable('vectors', embedFunction)
  } else {
    tbl = await createEmbeddingsTable(db, embedFunction)
  }

  // Use OpenAI Completion API to generate and answer based on the context that LanceDB provides
  const configuration = new Configuration({ apiKey })
  const openai = new OpenAIApi(configuration)
  const rl = readline.createInterface({ input, output })
  try {
    while (true) {
      const query = await rl.question('Prompt: ')
      const results = await tbl
        .search(query)
        .select(['title', 'text', 'context'])
        .limit(3)
        .execute()

      // console.table(results)

      const response = await openai.createCompletion({
        model: 'text-davinci-003',
        prompt: createPrompt(query, results),
        max_tokens: 400,
        temperature: 0,
        top_p: 1,
        frequency_penalty: 0,
        presence_penalty: 0
      })
      console.log(response.data.choices[0].text)
    }
  } catch (err) {
    console.log('Error: ', err)
  } finally {
    rl.close()
  }
  process.exit(1)
})()

async function createEmbeddingsTable (db, embedFunction) {
  console.log(`Creating embeddings from ${INPUT_FILE_NAME}`)
  // read the input file into a JSON array, skipping empty lines
  const lines = (await fs.readFile(INPUT_FILE_NAME, 'utf-8'))
    .toString()
    .split('\n')
    .filter(line => line.length > 0)
    .map(line => JSON.parse(line))

  const data = contextualize(lines, 20, 'video_id')
  return await db.createTable('vectors', data, embedFunction)
}

// Each transcript has a small text column, we include previous transcripts in order to
// have more context information when creating embeddings
function contextualize (rows, contextSize, groupColumn) {
  const grouped = []
  rows.forEach(row => {
    if (!grouped[row[groupColumn]]) {
      grouped[row[groupColumn]] = []
    }
    grouped[row[groupColumn]].push(row)
  })

  const data = []
  Object.keys(grouped).forEach(key => {
    for (let i = 0; i < grouped[key].length; i++) {
      const start = i - contextSize > 0 ? i - contextSize : 0
      grouped[key][i].context = grouped[key].slice(start, i + 1).map(r => r.text).join(' ')
    }
    data.push(...grouped[key])
  })
  return data
}

// Creates a prompt by aggregating all relevant contexts
function createPrompt (query, context) {
  let prompt =
      'Answer the question based on the context below.\n\n' +
      'Context:\n'

  // need to make sure our prompt is not larger than max size
  prompt = prompt + context.map(c => c.context).join('\n\n---\n\n').substring(0, 3750)
  prompt = prompt + `\n\nQuestion: ${query}\nAnswer:`
  return prompt
}