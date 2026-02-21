import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as path from 'path';

export class InfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // 1. Define the Lambda Function
    const fn = new lambda.Function(this, 'ApiFn', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../backend/app')),
      memorySize: 512,
      timeout: cdk.Duration.seconds(30), // AI needs time
      environment: {
        // The specific ID for Nova Micro in us-east-1
        MODEL_ID: 'us.amazon.nova-micro-v1:0',
      }
    });

    // 2. Grant Permission to Invoke Bedrock
    fn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel'],
      resources: ['*'],
    }));

    // 3. Define API Gateway
    const httpApi = new apigwv2.HttpApi(this, 'HttpApi', {
      apiName: 'bedrock-mock-interviewer-api',
    });

    // 4. Add Routes
    httpApi.addRoutes({
      path: '/health',
      methods: [apigwv2.HttpMethod.GET],
      integration: new integrations.HttpLambdaIntegration('HealthIntegration', fn),
    });

    httpApi.addRoutes({
      path: '/demo',
      methods: [apigwv2.HttpMethod.GET],
      integration: new integrations.HttpLambdaIntegration('DemoIntegration', fn),
    });

    new cdk.CfnOutput(this, 'ApiUrl', { value: httpApi.url ?? 'Something went wrong' });
  }
}