const fetch = require('node-fetch');
const fs = require('fs');
const dotenv = require('dotenv');
const { exit } = require('process');

dotenv.config();
const ZILLIZ_ENDPOINT = process.env.ZILLIZ_ENDPOINT;
const ZILLIZ_API_KEY = process.env.ZILLIZ_API_KEY;
const JOB_DESCRIPTION_FOLDER = './data/jobdescriptions/';

function readJobDescription(job) {
    return fs.readFileSync(JOB_DESCRIPTION_FOLDER + job + '.txt', 'utf8');
}

function validateModelArg(arg) {
    if (!['all-MiniLM-L6-v2', 'multi-qa-mpnet-base-dot-v1'].includes(arg)) {
        console.log(
            'Invalid model argument. Use either "all-MiniLM-L6-v2" or "multi-qa-mpnet-base-dot-v1"'
        );
        process.exit(1);
    }
    return arg;
}

function getCollection(model) {
    if (model === 'all-MiniLM-L6-v2') {
        return 'noc_data_cosine_all_MiniLM_L6_v2_with_384_dimensions';
    } else if (model === 'multi-qa-mpnet-base-dot-v1') {
        return 'noc_data_cosine_multi_qa_mpnet_base_dot_v1_with_768_dimensions';
    }
}

const job_description = readJobDescription(process.argv[2]);

const model_name = validateModelArg(process.argv[3]);

const collection_name = getCollection(model_name);

const url = `${ZILLIZ_ENDPOINT}/v1/vector/search`;

async function main() {
    const model_name = validateModelArg(process.argv[2]);
    const embedder = new DefaultEmbeddingFunction(model_name);

    return embedder.generate([job_description]).then((embedding) => {
        const body = JSON.stringify({
            collectionName: collection_name,
            vector: embedding,
            outputFields: ['noc_code', 'title', 'definition'],
            limit: 10,
        });
        const headers = {
            Authorization: `Bearer ${ZILLIZ_API_KEY}`,
            Accept: 'application/json',
            'Content-Type': 'application/json',
        };
        return fetch(url, {
            method: 'POST',
            headers: headers,
            body: body,
        })
            .then((response) => response.json())
            .then((result) => {
                console.log(JSON.stringify(result, null, 4));
            })
            .catch((error) => {
                console.error(error);
            });
    });
}
/*
fetch(url, {
    method: 'POST',
    headers: headers,
    body: body,
})
    .then((response) => response.json())
    .then((result) => {
        console.log(JSON.stringify(result, null, 4));
    })
    .catch((error) => {
        console.error(error);
    });
*/
