output "transcript_bucket" { value = aws_s3_bucket.transcripts.bucket }
output "launcher_function_name" { value = aws_lambda_function.launcher.function_name }
output "summarizer_function_name" { value = aws_lambda_function.summarizer.function_name }
output "dashboard_name" { value = aws_cloudwatch_dashboard.voice.dashboard_name }
output "summarizer_dead_letter_queue_arn" { value = aws_sqs_queue.summarizer_dlq.arn }
