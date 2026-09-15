terraform {
  backend "s3" {
    bucket       = "togglemaster-fase3-tfstate-377839494551"
    key          = "fase3/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}