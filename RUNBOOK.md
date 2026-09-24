# Voice Automation Operations Runbook

## Signal contract

- The launcher accepts an E.164 destination number and up to 32 Connect attributes.
- The launcher invokes an existing published contact flow on the configured Amazon Connect instance.
- The flow writes transcript JSON objects under `transcripts/` in the configured bucket.
- S3 invokes the summarizer for `.json` objects under that prefix.
- The summarizer writes a sibling object under `summaries/`, publishes `TranscriptsSummarized`, and never logs transcript content or phone numbers.
- Failed asynchronous summarizer invocations are sent to the encrypted SQS dead-letter queue.

## Service objectives

Suggested objectives for a production adaptation:

- At least 99.9% of valid call-launch invocations succeed each month.
- At least 99% of transcript objects produce summaries within five minutes.
- No failed transcript event remains in the dead-letter queue for more than one business day.

Track Lambda `Errors`, `Throttles`, and `Duration`; S3 notification failures; SQS queue depth and message age; and the `TranscriptsSummarized` metric.

## Call initiation issues

1. Confirm the Lambda has the correct Connect instance ID, published flow ID, and source number claimed by the instance.
2. Check Lambda errors and Connect contact search for the returned contact ID.
3. Verify the flow can dial the destination and that service quotas and regional calling rules permit it.
4. Check the configured outbound queue, hours of operation, and contact flow prompts.
5. Use a test destination you control and avoid repeatedly retrying a real call.

## Missing summaries

1. Confirm the contact flow wrote a JSON object beneath `transcripts/` and inspect its object metadata without exposing transcript content.
2. Verify S3 notification configuration, prefix/suffix filters, and the Lambda invoke permission.
3. Inspect summarizer Lambda logs for parsing, permission, timeout, or Bedrock errors.
4. Check `ApproximateNumberOfMessagesVisible` and `ApproximateAgeOfOldestMessage` on the dead-letter queue.
5. After fixing the cause, review and replay a dead-letter event, then confirm its matching output exists under `summaries/`.

## Bedrock errors

Confirm that the model ID is available in the configured region, the account has model access, and the summarizer role has `bedrock:InvokeModel` permission for that model. The empty model ID selects the deterministic extractive fallback. Do not send customer transcripts to a model until the data handling is approved for the environment.

## Recovery and privacy

Recovery is complete when a controlled test call finishes, the transcript arrives, a summary is written, the success metric increments, and the dead-letter queue is clear. Record the incident without placing phone numbers or transcript text in tickets or logs. Follow the organization's retention policy for versioned transcript objects.

## Rollback and cleanup

Review a Terraform plan before applying rollback changes. Disable the S3 notification or call-launch integration through a reviewed change if processing must stop. Keep the transcript data needed for investigation under the approved retention policy, then destroy only sandbox infrastructure after reviewing the resource plan.

