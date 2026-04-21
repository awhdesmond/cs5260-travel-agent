variable "project_id" {
  description = "The ID of the project in which to provision resources"
  type        = string
}

variable "region" {
  description = "The GCP region to deploy to"
  type        = string
  default     = "asia-southeast1"
}

variable "zone" {
  description = "The GCP zone to deploy to"
  type        = string
  default     = "asia-southeast1-a"
}

variable "machine_type" {
  description = "The machine type for the GCE instance"
  type        = string
  default     = "e2-medium"
}

variable "ssh_user" {
  description = "The SSH username to configure for the instance"
  type        = string
  default     = "ubuntu"
}

variable "ssh_pub_key_path" {
  description = "The path to the local public SSH key used to connect to the instance."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}
