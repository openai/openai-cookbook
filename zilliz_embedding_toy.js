const { DefaultEmbeddingFunction } = require('chromadb');
const json = require('json');

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
