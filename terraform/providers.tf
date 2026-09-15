provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = ["377839494551"]

  default_tags {
    tags = {
      Project     = "ToggleMaster"
      Phase       = "3"
      Environment = "academy"
      ManagedBy   = "Terraform"
    }
  }
}