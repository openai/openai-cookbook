const lancedb = require('vectordb')
const readline = require('readline/promises')
const { stdin: input, stdout: output } = require('process')
const fs = require('fs');
const Papa = require('papaparse');


(async () => {
  // You need to provide an OpenAI API key, here we read it from the OPENAI_API_KEY environment variable
  const apiKey = process.env.OPENAI_API_KEY

  const embedFunction = new lancedb.OpenAIEmbeddingFunction('id', apiKey)

  // // Connect to LanceDB
  const uri = 'data/sample-lancedb'
  const db = await lancedb.connect(uri)

  // create table with articles
  const tableName = 'wikipedia'
  let tbl
  if (!((await db.tableNames()).includes(tableName))) {
    // // Parse csv
    const fileData = fs.createReadStream('data/vector_database_wikipedia_articles_embedded.csv');
    Papa.parsePromise = function (file) {
      return new Promise(function (complete, error) {
        Papa.parse(file, { header: true, complete, error });
      });
    }
    const results = await Papa.parsePromise(fileData);
    
    // // Access the parsed data
    let articles = results.data;
    
    
    // We only need the title vector
    articles = articles.map(article => {
      article.vector = JSON.parse(article.title_vector)
      delete article.title_vector
      delete article.content_vector
      return article
    })
    
    tbl = await db.createTable(tableName, data=articles)
  }
  
  tbl = await db.openTable(tableName, embeddings=embedFunction)
  
  const rl = readline.createInterface({ input, output })

  try {
    while (true) {
      // Ask for queries
      const query = await rl.question('Query: ')
      const topk = await rl.question('Number of results to show: ')

      // Query
      const results = await tbl
        .search(query)
        .select(['title'])
        .limit(parseInt(topk))
        .execute()

      console.log(results.map(result => result.title))
    }
  } catch (err) {
    console.log('Error: ', err)
  } finally {
    rl.close()
  }
  process.exit(1)
})();