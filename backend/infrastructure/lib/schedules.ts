import * as cdk from "aws-cdk-lib";
import * as scheduler from "aws-cdk-lib/aws-scheduler";
import * as targets from "aws-cdk-lib/aws-scheduler-targets";
import type * as lambda from "aws-cdk-lib/aws-lambda";

/** Only the tick exists in this milestone. Later milestones add the rest. */
export function defineSchedules(scope: cdk.Stack, engineFn: lambda.IFunction) {
  new scheduler.Schedule(scope, "TickSchedule", {
    scheduleName: "findingalpha-tick",
    schedule: scheduler.ScheduleExpression.rate(cdk.Duration.minutes(15)),
    target: new targets.LambdaInvoke(engineFn, {
      input: scheduler.ScheduleTargetInput.fromObject({ job: "tick" }),
      retryAttempts: 0,
    }),
  });
}
