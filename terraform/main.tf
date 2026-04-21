# Artifact Registry for Docker images
resource "google_artifact_registry_repository" "docker_repo" {
  location      = var.region
  repository_id = "travel-agent-repo"
  description   = "Docker repository for Travel Agent Frontend and Backend"
  format        = "DOCKER"
}

# Static Public IP Address
resource "google_compute_address" "static_ip" {
  name = "travel-agent-static-ip"
}

# Firewall rule to allow SSH (22), HTTP (80), and HTTPS (443)
resource "google_compute_firewall" "allow_web_ssh" {
  name    = "allow-web-ssh"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22", "80", "443", "8000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["web-server"]
}

# Google Compute Engine Instance
resource "google_compute_instance" "app_server" {
  name         = "travel-agent-server"
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["web-server"]

  boot_disk {
    initialize_params {
      # Use Ubuntu 22.04 LTS
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 20
      type  = "pd-standard"
    }
  }

  network_interface {
    network = "default"
    access_config {
      nat_ip = google_compute_address.static_ip.address
    }
  }

  metadata = {
    ssh-keys = "${var.ssh_user}:${file(var.ssh_pub_key_path)}"
  }

  # Startup script to install Docker and Docker-Compose
  metadata_startup_script = <<-EOF
    #!/bin/bash
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=\"$(dpkg --print-architecture)\" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      \"$(. /etc/os-release && echo \"$VERSION_CODENAME\")\" stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Configure Docker so we can use it without sudo
    sudo usermod -aG docker ubuntu
    systemctl enable docker
    systemctl start docker

    # Configure docker to authenticate with GCP Artifact Registry
    sudo -u ubuntu gcloud auth configure-docker ${var.region}-docker.pkg.dev --quiet
  EOF

  # Ensure the instance has enough scopes to pull from Artifact Registry
  service_account {
    scopes = ["cloud-platform"]
  }
}
