data "aws_caller_identity" "current" {}

locals {
  name_prefix          = "voice-poc"
  connect_instance_arn = "arn:aws:connect:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${var.connect_instance_id}"
}

data "archive_file" "launcher" {
  type        = "zip"
  source_file = "${path.module}/../src/start_call.py"
  output_path = "${path.module}/start-call.zip"
}

data "archive_file" "summarizer" {
  type        = "zip"
  source_file = "${path.module}/../src/summarize_call.py"
  output_path = "${path.module}/summarize-call.zip"
}

resource "aws_s3_bucket" "transcripts" {
  bucket = var.transcript_bucket_name
}

resource "aws_s3_bucket_public_access_block" "transcripts" {
  bucket                  = aws_s3_bucket.transcripts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "transcripts" {
  bucket = aws_s3_bucket.transcripts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "transcripts" {
  bucket = aws_s3_bucket.transcripts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_sqs_queue" "summarizer_dlq" {
  name                      = "${local.name_prefix}-summarizer-dlq"
  sqs_managed_sse_enabled   = true
  message_retention_seconds = 1209600
}

resource "aws_iam_role" "launcher" {
  name               = "${local.name_prefix}-launcher-role"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role" "summarizer" {
  name               = "${local.name_prefix}-summarizer-role"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role_policy" "launcher" {
  role = aws_iam_role.launcher.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["connect:StartOutboundVoiceContact"], Resource = [local.connect_instance_arn, "${local.connect_instance_arn}/contact-flow/${var.contact_flow_id}"] },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.launcher.arn}:*" }
    ]
  })
}

resource "aws_iam_role_policy" "summarizer" {
  role = aws_iam_role.summarizer.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.transcripts.arn}/transcripts/*" },
      { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.transcripts.arn}/summaries/*" },
      { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.summarizer_dlq.arn },
      { Effect = "Allow", Action = ["cloudwatch:PutMetricData"], Resource = "*", Condition = { StringEquals = { "cloudwatch:namespace" = "VoiceAutomationPOC" } } },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.summarizer.arn}:*" }
    ], var.bedrock_model_id == "" ? [] : [{ Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}" }])
  })
}

resource "aws_cloudwatch_log_group" "launcher" {
  name              = "/aws/lambda/${local.name_prefix}-start-call"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "summarizer" {
  name              = "/aws/lambda/${local.name_prefix}-summarize-call"
  retention_in_days = 30
}

resource "aws_lambda_function" "launcher" {
  function_name                  = "${local.name_prefix}-start-call"
  role                           = aws_iam_role.launcher.arn
  runtime                        = "python3.12"
  handler                        = "start_call.handler"
  filename                       = data.archive_file.launcher.output_path
  source_code_hash               = data.archive_file.launcher.output_base64sha256
  timeout                        = 15
  memory_size                    = 128
  reserved_concurrent_executions = 5
  environment {
    variables = {
      CONNECT_INSTANCE_ID = var.connect_instance_id
      CONTACT_FLOW_ID     = var.contact_flow_id
      SOURCE_PHONE_NUMBER = var.source_phone_number
    }
  }
  depends_on = [aws_cloudwatch_log_group.launcher, aws_iam_role_policy.launcher]
}

resource "aws_lambda_function" "summarizer" {
  function_name                  = "${local.name_prefix}-summarize-call"
  role                           = aws_iam_role.summarizer.arn
  runtime                        = "python3.12"
  handler                        = "summarize_call.handler"
  filename                       = data.archive_file.summarizer.output_path
  source_code_hash               = data.archive_file.summarizer.output_base64sha256
  timeout                        = 60
  memory_size                    = 512
  reserved_concurrent_executions = 5
  environment {
    variables = {
      BEDROCK_MODEL_ID = var.bedrock_model_id
      METRIC_NAMESPACE = "VoiceAutomationPOC"
    }
  }
  dead_letter_config {
    target_arn = aws_sqs_queue.summarizer_dlq.arn
  }
  depends_on = [aws_cloudwatch_log_group.summarizer, aws_iam_role_policy.summarizer]
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowTranscriptBucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.summarizer.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.transcripts.arn
}

resource "aws_s3_bucket_notification" "transcripts" {
  bucket = aws_s3_bucket.transcripts.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.summarizer.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "transcripts/"
    filter_suffix       = ".json"
  }
  depends_on = [aws_lambda_permission.allow_s3]
}

resource "aws_cloudwatch_dashboard" "voice" {
  dashboard_name = "${local.name_prefix}-operations"
  dashboard_body = jsonencode({ widgets = [{ type = "metric", width = 12, height = 6, properties = { title = "Processed transcripts", region = var.aws_region, stat = "Sum", period = 300, metrics = [["VoiceAutomationPOC", "TranscriptsSummarized"]] } }] })
}
