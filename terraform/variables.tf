variable "aws_region" {
  type        = string
  description = "AWS region containing the Amazon Connect instance."
  default     = "us-east-1"
}

variable "connect_instance_id" {
  type        = string
  description = "Amazon Connect instance ID, not its ARN."
}

variable "contact_flow_id" {
  type        = string
  description = "Published Amazon Connect contact flow ID."
}

variable "source_phone_number" {
  type        = string
  description = "E.164 phone number claimed by the Connect instance."
  validation {
    condition     = can(regex("^\\+[1-9][0-9]{7,14}$", var.source_phone_number))
    error_message = "source_phone_number must use E.164 format."
  }
}

variable "bedrock_model_id" {
  type        = string
  description = "Optional Bedrock model ID. Empty uses extractive summarization."
  default     = ""
}

variable "transcript_bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name."
}
