const { DefaultEmbeddingFunction } = require('chromadb');
const json = require('json');
const fs = require('fs');

const JOB_DESCRIPTION_FOLDER = './data/jobdescriptions/';

function readJobDescription(job) {
    return fs.readFileSync(JOB_DESCRIPTION_FOLDER + job + '.txt', 'utf8');
}

const job_description = readJobDescription(process.argv[2]);

async function doIt() {
    console.log('hello0');
    const embedder = new DefaultEmbeddingFunction('all-MiniLM-L6-v2');
    console.log('hello1');
    return embedder.generate([job_description]).then((result) => {
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
