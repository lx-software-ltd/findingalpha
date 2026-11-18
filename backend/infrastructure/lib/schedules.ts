import * as cdk from "aws-cdk-lib";
import * as scheduler from "aws-cdk-lib/aws-scheduler";
import * as targets from "aws-cdk-lib/aws-scheduler-targets";
import type * as lambda from "aws-cdk-lib/aws-lambda";

/** Tick, the two ingest schedules, and the knowledge base check. A failed invoke is not retried. */
export function defineSchedules(scope: cdk.Stack, engineFn: lambda.IFunction) {
  const hongKong = cdk.TimeZone.of("Asia/Hong_Kong");
  new scheduler.Schedule(scope, "TickSchedule", {
    scheduleName: "findingalpha-tick",
    schedule: scheduler.ScheduleExpression.rate(cdk.Duration.minutes(15)),
    target: new targets.LambdaInvoke(engineFn, {
      input: scheduler.ScheduleTargetInput.fromObject({ job: "tick" }),
      retryAttempts: 0,
    }),
  });
  new scheduler.Schedule(scope, "IngestDailySchedule", {
    scheduleName: "findingalpha-ingest-daily",
    schedule: scheduler.ScheduleExpression.cron({
      minute: "0",
      hour: "12",
      weekDay: "TUE-SAT",
      timeZone: hongKong,
    }),
    target: new targets.LambdaInvoke(engineFn, {
      input: scheduler.ScheduleTargetInput.fromObject({ job: "ingest_daily" }),
      retryAttempts: 0,
    }),
  });
  new scheduler.Schedule(scope, "WeeklyRefreshSchedule", {
    scheduleName: "findingalpha-weekly-refresh",
    schedule: scheduler.ScheduleExpression.cron({
      minute: "0",
      hour: "8",
      weekDay: "SUN",
      timeZone: hongKong,
    }),
    target: new targets.LambdaInvoke(engineFn, {
      input: scheduler.ScheduleTargetInput.fromObject({ job: "weekly_refresh" }),
      retryAttempts: 0,
    }),
  });
  // The handler starts nothing until someone runs the job by hand once.
  new scheduler.Schedule(scope, "KbSyncCheckSchedule", {
    scheduleName: "findingalpha-kb-sync-check",
    schedule: scheduler.ScheduleExpression.cron({
      minute: "30",
      hour: "5",
      timeZone: hongKong,
    }),
    target: new targets.LambdaInvoke(engineFn, {
      input: scheduler.ScheduleTargetInput.fromObject({ job: "kb_sync_check" }),
      retryAttempts: 0,
    }),
  });
}
