import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as path from 'path';

export class InfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const fn = new lambda.Function(this, 'ApiFn', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../backend/app')),
      memorySize: 128,
    });

    const httpApi = new apigwv2.HttpApi(this, 'HttpApi', {
      apiName: 'bedrock-mock-interviewer-api',
    });

    httpApi.addRoutes({
      path: '/health',
      methods: [apigwv2.HttpMethod.GET],
      integration: new integrations.HttpLambdaIntegration('HealthIntegration', fn),
    });

    new cdk.CfnOutput(this, 'ApiUrl', { value: httpApi.url ?? 'Something went wrong' });
  }
}
