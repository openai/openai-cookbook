import { runProgress } from './lambda.mjs';

const [tableName, deploymentId, runId] = process.argv.slice(2);
if (!tableName || !/^[a-z][a-z0-9-]{2,39}$/.test(deploymentId ?? '') || !/^[a-f0-9]{64}$/.test(runId ?? '')) {
  throw new Error('Usage: node aws/run-status.mjs TABLE DEPLOYMENT_ID RUN_ID');
}
const [{ DynamoDBClient }, { DynamoDBDocumentClient, GetCommand }] = await Promise.all([
  import('@aws-sdk/client-dynamodb'), import('@aws-sdk/lib-dynamodb'),
]);
const client = DynamoDBDocumentClient.from(new DynamoDBClient({ maxAttempts: 3 }));
const { Item } = await client.send(new GetCommand({ TableName: tableName, ConsistentRead: true,
  Key: { PK: `RUN#${deploymentId}#${runId}`, SK: 'PROGRESS' } }));
if (!Item) throw new Error('RUN_NOT_FOUND');
console.log(JSON.stringify(runProgress(Item), null, 2));
