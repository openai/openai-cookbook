const { DefaultEmbeddingFunction } = require('chromadb');

/*
function helloWorld() {
  return new Promise(resolve => {
    setTimeout(() => {
      resolve('Hello World!');
    }, 2000);
  });
}

const msg = async function() { //Async Function Expression
  const msg = await helloWorld();
  console.log('Message:', msg);
}

const msg1 = async () => { //Async Arrow Function
  const msg = await helloWorld();
  console.log('Message:', msg);
}

msg(); // Message: Hello World! <-- after 2 seconds
msg1(); // Message: Hello World

*/

async function doIt() {
    console.log('hello0');
    const embedder = new DefaultEmbeddingFunction('all-MiniLM-L6-v2');
    console.log('hello1');
    return embedder.generate(['document1', 'document2']).then((result) => {
        console.log('hello2');
        console.log(result);
        console.log('hello3');
        return result;
    });
}

doIt().then((result) => {
    console.log('hello4');
    console.log(json.stringify(result));
    console.log('hello5');
});
