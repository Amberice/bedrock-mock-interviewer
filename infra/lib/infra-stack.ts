import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as path from 'path';

export class InfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // 1. DynamoDB Table
    const table = new dynamodb.Table(this, 'SessionTable', {
      partitionKey: { name: 'session_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY, 
    });

    // 2. Lambda Function
    const fn = new lambda.Function(this, 'ApiFn', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../backend/app')),
      memorySize: 512,
      timeout: cdk.Duration.seconds(30),
      environment: {
        MODEL_ID: 'us.amazon.nova-micro-v1:0',
        TABLE_NAME: table.tableName,
      },
    });

    // 3. Permissions
    fn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel'],
      resources: ['*'],
    }));
    
    table.grantReadWriteData(fn); 

    // 4. API Gateway with CORS (FIXED: Using CorsHttpMethod)
    const httpApi = new apigwv2.HttpApi(this, 'HttpApi', {
      apiName: 'bedrock-mock-interviewer-api',
      corsPreflight: {
        allowHeaders: ['Content-Type'],
        allowMethods: [
          apigwv2.CorsHttpMethod.GET, 
          apigwv2.CorsHttpMethod.POST, 
          apigwv2.CorsHttpMethod.OPTIONS
        ],
        allowOrigins: ['*'],
      },
    });

    // 5. Routes (These still use HttpMethod, which is correct here)
    httpApi.addRoutes({
      path: '/health',
      methods: [apigwv2.HttpMethod.GET],
      integration: new integrations.HttpLambdaIntegration('HealthIntegration', fn),
    });

    httpApi.addRoutes({
      path: '/chat',
      methods: [apigwv2.HttpMethod.POST],
      integration: new integrations.HttpLambdaIntegration('ChatIntegration', fn),
    });

    new cdk.CfnOutput(this, 'ApiUrl', { value: httpApi.url ?? 'Something went wrong' });
  }
}
