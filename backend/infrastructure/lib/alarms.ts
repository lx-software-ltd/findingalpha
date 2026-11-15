import * as cdk from "aws-cdk-lib";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import type * as lambda from "aws-cdk-lib/aws-lambda";
import type * as sqs from "aws-cdk-lib/aws-sqs";

export function defineAlarms(
  scope: cdk.Stack,
  functions: lambda.Function[],
  deadLetterQueue: sqs.Queue,
) {
  for (const fn of functions) {
    new cloudwatch.Alarm(scope, `${fn.node.id}Errors`, {
      metric: fn.metricErrors({ period: cdk.Duration.minutes(15), statistic: "Sum" }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      alarmDescription: `One error on ${fn.node.id} in 15 minutes.`,
    });
  }
  new cloudwatch.Alarm(scope, "DeadLetterVisible", {
    metric: deadLetterQueue.metricApproximateNumberOfMessagesVisible({
      period: cdk.Duration.minutes(5),
      statistic: "Maximum",
    }),
    threshold: 1,
    evaluationPeriods: 1,
    comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
    treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    alarmDescription: "The Lambda dead-letter queue has a visible message.",
  });
}
