const { DefaultEmbeddingFunction } = require('chromadb');
const fs = require('fs');
const dotenv = require('dotenv');

dotenv.config();
const ZILLIZ_ENDPOINT = process.env.ZILLIZ_ENDPOINT;
const ZILLIZ_API_KEY = process.env.ZILLIZ_API_KEY;
const JOB_DESCRIPTION_FOLDER = './data/jobdescriptions/';

function readJobDescription(job) {
    return fs.readFileSync(JOB_DESCRIPTION_FOLDER + job + '.txt', 'utf8');
}

function validateModelArgument(arg) {
    if (!['all-MiniLM-L6-v2', 'multi-qa-mpnet-base-dot-v1'].includes(arg)) {
        console.log(
            'Invalid model argument. Use either "all-MiniLM-L6-v2" or "multi-qa-mpnet-base-dot-v1"'
        );
        process.exit(1);
    }
    return arg;
}

function getCollectionForModel(model) {
    if (model === 'all-MiniLM-L6-v2') {
        return 'noc_data_cosine_all_MiniLM_L6_v2_with_384_dimensions';
    } else if (model === 'multi-qa-mpnet-base-dot-v1') {
        return 'noc_data_cosine_multi_qa_mpnet_base_dot_v1_with_768_dimensions';
    }
}

const jobDescription = readJobDescription(process.argv[2]);
const modelName = validateModelArgument(process.argv[3]);
const collectionName = getCollectionForModel(modelName);

async function main() {
    console.log('modelName:', modelName);
    const embedder = new DefaultEmbeddingFunction(modelName);
    return embedder.generate([jobDescription]).
        then((embedding) => {

            console.log('collectionName:', collectionName);
            console.log('embedding size:', embedding[0].length);

            const url = `${ZILLIZ_ENDPOINT}/v1/vector/search`;
            const headers = {
                Authorization: `Bearer ${ZILLIZ_API_KEY}`,
                Accept: 'application/json',
                'Content-Type': 'application/json',
            };
            const body = JSON.stringify({
                collectionName: collectionName,
                vector: embedding[0],
                outputFields: ['noc_code', 'title', 'definition'],
                limit: 10,
            });
            return fetch(url, {
                method: 'POST',
                headers: headers,
                body: body,
            }).
            then((response) => response.json());
        });
}

main().then((result) => {
    console.log(result);
});
