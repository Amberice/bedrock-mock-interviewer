import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as iam from 'aws-cdk-lib/aws-iam';

export class InfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // 1. The Database
    const table = new dynamodb.Table(this, 'SessionTable', {
      partitionKey: { name: 'session_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // 2. The Compute
    const backend = new lambda.Function(this, 'BackendFunction', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      // CHECK THIS: Ensure handler.py is directly inside the 'backend' folder
      code: lambda.Code.fromAsset('../backend/app'),
      environment: {
        TABLE_NAME: table.tableName,
        MODEL_ID: "us.amazon.nova-micro-v1:0",
      },
      timeout: cdk.Duration.seconds(30),
    });

    // 3. The API Gateway (Corrected to Proxy Mode)
    const api = new apigateway.LambdaRestApi(this, 'API', {
      handler: backend,
      // CRITICAL FIX: Set to true. This allows the Lambda to handle the /chat route automatically.
      proxy: true,
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'Authorization'],
      },
    });

    // Note: When proxy is true, we DO NOT manually add resources like .addResource('chat')
    // The Lambda handles all routes automatically.

    // --- PERMISSIONS ---
    table.grantReadWriteData(backend);

    // Allow Bedrock
    backend.addToRolePolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel', 'bedrock:Converse'],
      resources: ['*'],
    }));

    // Allow Polly (Day 6 Voice)
    backend.addToRolePolicy(new iam.PolicyStatement({
      actions: ['polly:SynthesizeSpeech'],
      resources: ['*'],
    }));
  }
}