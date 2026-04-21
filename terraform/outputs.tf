output "instance_name" {
  description = "The name of the GCE instance"
  value       = google_compute_instance.app_server.name
}

output "instance_public_ip" {
  description = "The static public IP of the instance"
  value       = google_compute_address.static_ip.address
}

output "artifact_registry_repo_url" {
  description = "The Artifact Registry URL where Docker images should be pushed"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker_repo.name}"
}

output "ssh_command" {
  description = "The command to SSH into the instance"
  value       = "ssh -i ${replace(var.ssh_pub_key_path, ".pub", "")} ${var.ssh_user}@${google_compute_address.static_ip.address}"
}
