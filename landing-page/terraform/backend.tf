terraform {
  backend "s3" {
    bucket  = "dephealth-terraform-state"
    key     = "landing-page/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
