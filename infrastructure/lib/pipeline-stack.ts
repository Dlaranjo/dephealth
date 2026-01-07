import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as lambdaEventSources from "aws-cdk-lib/aws-lambda-event-sources";
import { Construct } from "constructs";
import * as path from "path";

interface PipelineStackProps extends cdk.StackProps {
  packagesTable: dynamodb.Table;
  rawDataBucket: s3.Bucket;
}

export class PipelineStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: PipelineStackProps) {
    super(scope, id, props);

    const { packagesTable, rawDataBucket } = props;

    // ===========================================
    // Secrets Manager: GitHub Token
    // ===========================================
    // Create a secret placeholder - actual value must be set manually
    const githubTokenSecret = new secretsmanager.Secret(
      this,
      "GitHubTokenSecret",
      {
        secretName: "dephealth/github-token",
        description: "GitHub Personal Access Token for API access",
      }
    );

    // ===========================================
    // SQS: Package Processing Queues
    // ===========================================

    // Dead letter queue for failed messages
    const dlq = new sqs.Queue(this, "PackageQueueDLQ", {
      queueName: "dephealth-package-dlq",
      retentionPeriod: cdk.Duration.days(14),
    });

    // Main queue for package processing jobs
    // Visibility timeout should be 6x Lambda timeout to prevent message reprocessing
    const packageQueue = new sqs.Queue(this, "PackageQueue", {
      queueName: "dephealth-package-queue",
      visibilityTimeout: cdk.Duration.minutes(6), // > Lambda timeout (5 min)
      deadLetterQueue: {
        queue: dlq,
        maxReceiveCount: 3,
      },
    });

    // ===========================================
    // Lambda: Common configuration
    // ===========================================
    const functionsDir = path.join(__dirname, "../../functions");

    const commonLambdaProps = {
      runtime: lambda.Runtime.PYTHON_3_12,
      memorySize: 256,
      timeout: cdk.Duration.minutes(2),
      environment: {
        PACKAGES_TABLE: packagesTable.tableName,
        RAW_DATA_BUCKET: rawDataBucket.bucketName,
        GITHUB_TOKEN_SECRET_ARN: githubTokenSecret.secretArn,
        PACKAGE_QUEUE_URL: packageQueue.queueUrl,
      },
    };

    // ===========================================
    // Lambda: Refresh Dispatcher
    // ===========================================
    // Triggered by EventBridge schedule, enqueues packages for refresh
    const refreshDispatcher = new lambda.Function(this, "RefreshDispatcher", {
      ...commonLambdaProps,
      functionName: "dephealth-refresh-dispatcher",
      handler: "refresh_dispatcher.handler",
      code: lambda.Code.fromAsset(path.join(functionsDir, "collectors")),
      description: "Dispatches package refresh jobs to SQS based on tier",
    });

    packagesTable.grantReadData(refreshDispatcher);
    packageQueue.grantSendMessages(refreshDispatcher);

    // ===========================================
    // Lambda: Package Collector
    // ===========================================
    // Processes packages from SQS queue
    const packageCollector = new lambda.Function(this, "PackageCollector", {
      ...commonLambdaProps,
      functionName: "dephealth-package-collector",
      handler: "package_collector.handler",
      code: lambda.Code.fromAsset(path.join(functionsDir, "collectors")),
      timeout: cdk.Duration.minutes(5),
      description: "Collects data from deps.dev, npm, and GitHub",
    });

    packagesTable.grantReadWriteData(packageCollector);
    rawDataBucket.grantWrite(packageCollector);
    githubTokenSecret.grantRead(packageCollector);

    // Connect collector to SQS queue
    packageCollector.addEventSource(
      new lambdaEventSources.SqsEventSource(packageQueue, {
        batchSize: 5,
        maxConcurrency: 2, // Limit concurrent executions to respect rate limits
      })
    );

    // ===========================================
    // Lambda: Score Calculator
    // ===========================================
    // Calculates health scores after data collection
    // Triggered by DynamoDB Streams when package data is updated
    const scoreCalculator = new lambda.Function(this, "ScoreCalculator", {
      ...commonLambdaProps,
      functionName: "dephealth-score-calculator",
      handler: "score_package.handler",
      code: lambda.Code.fromAsset(path.join(functionsDir, "scoring")),
      description: "Calculates health scores for packages",
    });

    packagesTable.grantReadWriteData(scoreCalculator);

    // Add DynamoDB Streams trigger to calculate scores after data collection
    scoreCalculator.addEventSource(
      new lambdaEventSources.DynamoEventSource(packagesTable, {
        startingPosition: lambda.StartingPosition.LATEST,
        batchSize: 10,
        retryAttempts: 3,
        // Only trigger on INSERT and MODIFY, not DELETE
        filters: [
          lambda.FilterCriteria.filter({
            eventName: lambda.FilterRule.or("INSERT", "MODIFY"),
          }),
        ],
      })
    );

    // ===========================================
    // EventBridge: Scheduled Triggers
    // ===========================================

    // Daily refresh at 2:00 AM UTC
    new events.Rule(this, "DailyRefreshRule", {
      ruleName: "dephealth-daily-refresh",
      schedule: events.Schedule.cron({ hour: "2", minute: "0" }),
      description: "Triggers daily package refresh for Tier 1 packages",
      targets: [
        new targets.LambdaFunction(refreshDispatcher, {
          event: events.RuleTargetInput.fromObject({
            tier: 1,
            reason: "daily_refresh",
          }),
        }),
      ],
    });

    // Every 3 days refresh (Tier 2) - runs at 3:00 AM on days 1, 4, 7, 10, 13, 16, 19, 22, 25, 28
    new events.Rule(this, "ThreeDayRefreshRule", {
      ruleName: "dephealth-three-day-refresh",
      schedule: events.Schedule.expression(
        "cron(0 3 1,4,7,10,13,16,19,22,25,28 * ? *)"
      ),
      description: "Triggers 3-day package refresh for Tier 2 packages",
      targets: [
        new targets.LambdaFunction(refreshDispatcher, {
          event: events.RuleTargetInput.fromObject({
            tier: 2,
            reason: "three_day_refresh",
          }),
        }),
      ],
    });

    // Weekly refresh (Tier 3) - runs at 4:00 AM on Sundays
    new events.Rule(this, "WeeklyRefreshRule", {
      ruleName: "dephealth-weekly-refresh",
      schedule: events.Schedule.cron({
        hour: "4",
        minute: "0",
        weekDay: "SUN",
      }),
      description: "Triggers weekly package refresh for Tier 3 packages",
      targets: [
        new targets.LambdaFunction(refreshDispatcher, {
          event: events.RuleTargetInput.fromObject({
            tier: 3,
            reason: "weekly_refresh",
          }),
        }),
      ],
    });

    // ===========================================
    // CloudWatch Alarms
    // ===========================================
    // TODO: Add alarms for:
    // - DLQ message count > 0
    // - Lambda error rate > 1%
    // - DynamoDB throttling

    // ===========================================
    // Outputs
    // ===========================================
    new cdk.CfnOutput(this, "PackageQueueUrl", {
      value: packageQueue.queueUrl,
      description: "SQS queue URL for package processing",
      exportName: "DepHealthPackageQueueUrl",
    });

    new cdk.CfnOutput(this, "GitHubTokenSecretArn", {
      value: githubTokenSecret.secretArn,
      description: "GitHub token secret ARN (set value manually)",
      exportName: "DepHealthGitHubTokenSecretArn",
    });
  }
}
