const { Client } = require('@microsoft/microsoft-graph-client');
const { Buffer } = require('buffer');
const path = require('path');
const axios = require('axios');
const qs = require('querystring');


//// --------- ENVIRONMENT CONFIGURATION AND INITIALIZATION ---------
// Function to initialize Microsoft Graph client
const initGraphClient = (accessToken) => {
    return Client.init({
        authProvider: (done) => {
            done(null, accessToken); // Pass the access token for Graph API calls
        }
    });
};

//// --------- AUTHENTICATION AND TOKEN MANAGEMENT ---------
// Function to obtain OBO token. This will take the access token in request header (scoped to this Function App) and generate a new token to use for Graph API
const getOboToken = async (userAccessToken) => {
    const { TENANT_ID, CLIENT_ID,  MICROSOFT_PROVIDER_AUTHENTICATION_SECRET } = process.env;
    const scope = 'https://graph.microsoft.com/.default';
    const oboTokenUrl = `https://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/token`;

    const params = {
        client_id: CLIENT_ID,
        client_secret: MICROSOFT_PROVIDER_AUTHENTICATION_SECRET,
        grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        assertion: userAccessToken,
        requested_token_use: 'on_behalf_of',
        scope: scope
    };

    try {
        const response = await axios.post(oboTokenUrl, qs.stringify(params), {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        });
        return response.data.access_token; // OBO token
    } catch (error) {
        console.error('Error obtaining OBO token:', error.response?.data || error.message);
        throw error;
    }
};
//// --------- DOCUMENT PROCESSING ---------
// Function to fetch drive item content and convert to text

const getDriveItemContent = async (client, driveId, itemId, name) => {
    try {
        // const fileType = path.extname(name).toLowerCase();
        // the below files types are the ones that are able to be converted to PDF to extract the text. See https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0&tabs=http
        // const allowedFileTypes = ['.pdf', '.doc', '.docx', '.odp', '.ods', '.odt', '.pot', '.potm', '.potx', '.pps', '.ppsx', '.ppsxm', '.ppt', '.pptm', '.pptx', '.rtf'];
        // filePath changes based on file type, adding ?format=pdf to convert non-pdf types to pdf for text extraction, so all files in allowedFileTypes above are converted to pdf
        const filePath = `/drives/${driveId}/items/${itemId}`;
        const downloadPath = filePath + `/content`
        const fileStream = await client.api(downloadPath).getStream();
        let chunks = [];
            for await (let chunk of fileStream) {
                chunks.push(chunk);
            }
        const base64String = Buffer.concat(chunks).toString('base64');
        const file = await client.api(filePath).get();
        const mime_type = file.file.mimeType;
        const name = file.name;
        return {"name":name, "mime_type":mime_type, "content":base64String}
    } catch (error) {
        console.error('Error fetching drive content:', error);
        throw new Error(`Failed to fetch content for ${name}: ${error.message}`);
    }
};


//// --------- AZURE FUNCTION LOGIC ---------
// Below is what the Azure Function executes
module.exports = async function (context, req) {
    // const query = req.query.query || (req.body && req.body.query);
    const searchTerm = req.query.searchTerm || (req.body && req.body.searchTerm);
    if (!req.headers.authorization) {
        context.res = {
            status: 400,
            body: 'Authorization header is missing'
        };
        return;
    }
    /// The below takes the token passed to the function, to use to get an OBO token.
    const bearerToken = req.headers.authorization.split(' ')[1];
    let accessToken;
    try {
        accessToken = await getOboToken(bearerToken);
    } catch (error) {
        context.res = {
            status: 500,
            body: `Failed to obtain OBO token: ${error.message}`
        };
        return;
    }
    // Initialize the Graph Client using the initGraphClient function defined above
    let client = initGraphClient(accessToken);
    // this is the search body to be used in the Microsft Graph Search API: https://learn.microsoft.com/en-us/graph/search-concept-files
    const requestBody = {
        requests: [
            {
                entityTypes: ['driveItem'],
                query: {
                    queryString: searchTerm
                },
                from: 0,
                // the below is set to summarize the top 10 search results from the Graph API, but can configure based on your documents. 
                size: 10
            }
        ]
    };

    try { 
        // This is where we are doing the search
        const list = await client.api('/search/query').post(requestBody);

        const processList = async () => {
            // This will go through and for each search response, grab the contents of the file and summarize with gpt-3.5-turbo
            const results = [];

            await Promise.all(list.value[0].hitsContainers.map(async (container) => {
                for (const hit of container.hits) {
                    if (hit.resource["@odata.type"] === "#microsoft.graph.driveItem") {
                        const { name, id } = hit.resource;
                        const driveId = hit.resource.parentReference.driveId;
                        const contents = await getDriveItemContent(client, driveId, id, name);
                        results.push(contents)
                    }
                }
            }));

            return results;
        };
        let results;
        if (list.value[0].hitsContainers[0].total == 0) {
            // Return no results found to the API if the Microsoft Graph API returns no results
            results = 'No results found';
        } else {
            // If the Microsoft Graph API does return results, then run processList to iterate through.
            results = await processList();
            results = {'openaiFileResponse': results}
            // results.sort((a, b) => a.rank - b.rank);
        }
        context.res = {
            status: 200,
            body: results
        };
    } catch (error) {
        context.res = {
            status: 500,
            body: `Error performing search or processing results: ${error.message}`,
        };
    }
};

