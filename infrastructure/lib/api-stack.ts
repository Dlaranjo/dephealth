import * as cdk from "aws-cdk-lib";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as logs from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";
import * as path from "path";

interface ApiStackProps extends cdk.StackProps {
  packagesTable: dynamodb.Table;
  apiKeysTable: dynamodb.Table;
}

export class ApiStack extends cdk.Stack {
  public readonly api: apigateway.RestApi;

  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);

    const { packagesTable, apiKeysTable } = props;

    // ===========================================
    // Secrets Manager: Stripe Secrets
    // ===========================================
    const stripeSecret = new secretsmanager.Secret(this, "StripeSecret", {
      secretName: "dephealth/stripe-secret",
      description: "Stripe API secret key",
    });

    const stripeWebhookSecret = new secretsmanager.Secret(
      this,
      "StripeWebhookSecret",
      {
        secretName: "dephealth/stripe-webhook",
        description: "Stripe webhook signing secret",
      }
    );

    // ===========================================
    // Lambda: Common configuration
    // ===========================================
    const functionsDir = path.join(__dirname, "../../functions");

    // Bundle API handlers with shared module
    // Uses bundling to copy both api/ and shared/ directories
    const apiCodeWithShared = lambda.Code.fromAsset(functionsDir, {
      bundling: {
        image: lambda.Runtime.PYTHON_3_12.bundlingImage,
        command: [
          "bash",
          "-c",
          [
            "cp -r /asset-input/api/* /asset-output/",
            "cp -r /asset-input/shared /asset-output/",
            "pip install -r /asset-input/api/requirements.txt -t /asset-output/ --quiet",
          ].join(" && "),
        ],
      },
    });

    const commonLambdaProps = {
      runtime: lambda.Runtime.PYTHON_3_12,
      memorySize: 256,
      timeout: cdk.Duration.seconds(30),
      environment: {
        PACKAGES_TABLE: packagesTable.tableName,
        API_KEYS_TABLE: apiKeysTable.tableName,
        STRIPE_SECRET_ARN: stripeSecret.secretArn,
        STRIPE_WEBHOOK_SECRET_ARN: stripeWebhookSecret.secretArn,
      },
    };

    // ===========================================
    // Lambda: API Handlers
    // ===========================================

    // Health check handler (no auth required)
    const healthHandler = new lambda.Function(this, "HealthHandler", {
      ...commonLambdaProps,
      functionName: "dephealth-api-health",
      handler: "health.handler",
      code: apiCodeWithShared,
      description: "API health check endpoint",
    });

    // Get package handler
    const getPackageHandler = new lambda.Function(this, "GetPackageHandler", {
      ...commonLambdaProps,
      functionName: "dephealth-api-get-package",
      handler: "get_package.handler",
      code: apiCodeWithShared,
      description: "Get package health score",
    });

    packagesTable.grantReadData(getPackageHandler);
    apiKeysTable.grantReadWriteData(getPackageHandler);

    // Scan packages handler
    const scanHandler = new lambda.Function(this, "ScanHandler", {
      ...commonLambdaProps,
      functionName: "dephealth-api-scan",
      handler: "post_scan.handler",
      code: apiCodeWithShared,
      timeout: cdk.Duration.seconds(60),
      memorySize: 512,
      description: "Scan package.json for health scores",
    });

    packagesTable.grantReadData(scanHandler);
    apiKeysTable.grantReadWriteData(scanHandler);

    // Get usage handler
    const getUsageHandler = new lambda.Function(this, "GetUsageHandler", {
      ...commonLambdaProps,
      functionName: "dephealth-api-get-usage",
      handler: "get_usage.handler",
      code: apiCodeWithShared,
      description: "Get API usage statistics",
    });

    apiKeysTable.grantReadData(getUsageHandler);

    // Stripe webhook handler
    const stripeWebhookHandler = new lambda.Function(
      this,
      "StripeWebhookHandler",
      {
        ...commonLambdaProps,
        functionName: "dephealth-api-stripe-webhook",
        handler: "stripe_webhook.handler",
        code: apiCodeWithShared,
        description: "Handle Stripe webhook events",
      }
    );

    apiKeysTable.grantReadWriteData(stripeWebhookHandler);
    stripeSecret.grantRead(stripeWebhookHandler);
    stripeWebhookSecret.grantRead(stripeWebhookHandler);

    // ===========================================
    // API Gateway
    // ===========================================
    this.api = new apigateway.RestApi(this, "DepHealthApi", {
      restApiName: "DepHealth API",
      description: "Dependency Health Intelligence API",
      deployOptions: {
        stageName: "v1",
        throttlingBurstLimit: 100,
        throttlingRateLimit: 50,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: false,
        metricsEnabled: true,
      },
      defaultCorsPreflightOptions: {
        // Restrict CORS to specific origins in production
        // Update these URLs after deployment
        allowOrigins: [
          "https://dephealth.laranjo.dev",
          "https://app.dephealth.laranjo.dev",
          "http://localhost:3000", // For local development
          "http://localhost:4321", // Astro dev server
        ],
        allowMethods: ["GET", "POST", "OPTIONS"],
        allowHeaders: [
          "Content-Type",
          "X-API-Key",
          "X-Amz-Date",
          "Authorization",
        ],
      },
    });

    // ===========================================
    // API Routes
    // ===========================================

    // GET /health (no auth)
    const healthResource = this.api.root.addResource("health");
    healthResource.addMethod(
      "GET",
      new apigateway.LambdaIntegration(healthHandler)
    );

    // GET /packages/{ecosystem}/{name}
    const packagesResource = this.api.root.addResource("packages");
    const ecosystemResource = packagesResource.addResource("{ecosystem}");
    const packageNameResource = ecosystemResource.addResource("{name}");
    packageNameResource.addMethod(
      "GET",
      new apigateway.LambdaIntegration(getPackageHandler)
    );

    // POST /scan
    const scanResource = this.api.root.addResource("scan");
    scanResource.addMethod(
      "POST",
      new apigateway.LambdaIntegration(scanHandler)
    );

    // GET /usage
    const usageResource = this.api.root.addResource("usage");
    usageResource.addMethod(
      "GET",
      new apigateway.LambdaIntegration(getUsageHandler)
    );

    // POST /webhooks/stripe (no auth - uses Stripe signature)
    const webhooksResource = this.api.root.addResource("webhooks");
    const stripeWebhookResource = webhooksResource.addResource("stripe");
    stripeWebhookResource.addMethod(
      "POST",
      new apigateway.LambdaIntegration(stripeWebhookHandler)
    );

    // ===========================================
    // Outputs
    // ===========================================
    new cdk.CfnOutput(this, "ApiUrl", {
      value: this.api.url,
      description: "API Gateway URL",
      exportName: "DepHealthApiUrl",
    });

    new cdk.CfnOutput(this, "StripeSecretArn", {
      value: stripeSecret.secretArn,
      description: "Stripe secret ARN (set value manually)",
      exportName: "DepHealthStripeSecretArn",
    });

    new cdk.CfnOutput(this, "StripeWebhookSecretArn", {
      value: stripeWebhookSecret.secretArn,
      description: "Stripe webhook secret ARN (set value manually)",
      exportName: "DepHealthStripeWebhookSecretArn",
    });
  }
}
