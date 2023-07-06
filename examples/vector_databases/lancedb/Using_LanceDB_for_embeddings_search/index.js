const lancedb = require('vectordb')
const readline = require('readline/promises')
const { stdin: input, stdout: output } = require('process')
const fs = require('fs');
const Papa = require('papaparse');


(async () => {
    // Parse csv
    const fileData = fs.createReadStream('../data/vector_database_wikipedia_articles_embedded.csv');
    Papa.parsePromise = function(file) {
      return new Promise(function(complete, error) {
        Papa.parse(file, { header: true, complete, error });
      });
    }
    const results = await Papa.parsePromise(fileData);

    // Access the parsed data
    let articles = results.data;


    articles = articles.map(article => {
      article.vector = JSON.parse(article.title_vector)
      article.title_vector = null
      if (article.vector.length != 1536) {
        console.log(article.vector)
      }
      article.content_vector = JSON.parse(article.content_vector)
      return article 
    })

    // console.log(Object.articles[0])

    // You need to provide an OpenAI API key, here we read it from the OPENAI_API_KEY environment variable
    const apiKey = process.env.OPENAI_API_KEY

    const embedFunction = new lancedb.OpenAIEmbeddingFunction('id', apiKey)

    // Connect to LanceDB
    const uri = "data/sample-lancedb"
    const db = await lancedb.connect(uri)
  
    console.log(articles[0])
    // create table with articles
    let tbl = await db.createTable("wikipedia", data=[articles[0]])

    // open table so that embeddings are generated for queries
    // tbl = await db.openTable("wikipedia", embedFunction)
    
    const rl = readline.createInterface({ input, output })

    try {
      while (true) {
        // Ask for queries
        const query = await rl.question('Query: ')
        const topk = await rl.question('Number of results to show: ')

        // Query
        const results = await tbl
          .search(query)
          .limit(parseInt(topk))
          .execute()

        console.log(results)
      }
    } catch (err) {
      console.log('Error: ', err)
    } finally {
      rl.close()
    }
    process.exit(1)
})();