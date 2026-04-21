# DevOps & Deployment Guide

This guide details the steps to build the application container images, push them to the Google Artifact Registry (GCR replacement), and deploy our cloud infrastructure using Terraform.

---

## 1. Deploying the Cloud Infrastructure (Terraform)

The Terraform setup provisions our infrastructure containing:
- A Google Compute Engine instance
- A Static Public IP
- An Artifact Registry Repository
- Firewall rules

### Prerequisites
- Install [Terraform](https://developer.hashicorp.com/terraform/downloads).
- Install the [Google Cloud CLI (`gcloud`)](https://cloud.google.com/sdk/docs/install).

### Steps
1. Authenticate to your GCP project:
   ```bash
   gcloud auth login
   ```
2. Navigate to the Terraform folder:
   ```bash
   cd terraform
   ```
3. Copy the variables example file and add your Project ID:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```
   *Edit `terraform.tfvars` and set your specific GCP Project ID.*
4. Initialize the Terraform directory plugin logic:
   ```bash
   terraform init
   ```
5. Preview the infrastructure plan:
   ```bash
   terraform plan
   ```
6. Apply the configuration. You will be prompted to type `yes` to confirm:
   ```bash
   terraform apply
   ```

After applying, Terraform will output your `artifact_registry_repo_url`, `instance_public_ip`, and `ssh_command`. Keep these handy.

---

## 2. Building and Pushing Docker Images

Once the Artifact Registry is provisioned by Terraform, you can push the frontend and backend Docker containers to it.

### Prerequisites
Ensure your local Docker daemon is running, and authenticate Docker with GCP's Artifact Registry:
```bash
# General format: gcloud auth configure-docker <REGION>-docker.pkg.dev
gcloud auth configure-docker asia-southeast1-docker.pkg.dev
```

### Steps

Replace the placeholders below using the Terraform outputs you got:
- `REGION`: Try `asia-southeast1` if you used defaults.
- `PROJECT_ID`: Your GCP Project account.
- `REPO`: Generally `travel-agent-repo` (if using terraform defaults).

#### Frontend Image
1. From the project root directory, build the frontend image:
   ```bash
   docker build --platform linux/amd64 -t frontend ./frontend
   ```
2. Tag the image for the Artifact Registry:
   ```bash
   docker tag frontend asia-southeast1-docker.pkg.dev/cs5260-travel-agent/travel-agent-repo/frontend:1.0.0
   ```
3. Push the image:
   ```bash
   docker push asia-southeast1-docker.pkg.dev/cs5260-travel-agent/travel-agent-repo/frontend:1.0.0
   ```

#### Backend Image
1. From the project root directory, build the backend image:
   ```bash
   docker build --platform linux/amd64 -t backend ./backend
   ```
2. Tag the image for the Artifact Registry:
   ```bash
   docker tag backend asia-southeast1-docker.pkg.dev/cs5260-travel-agent/travel-agent-repo/backend:1.0.0
   ```
3. Push the image:
   ```bash
   docker push asia-southeast1-docker.pkg.dev/cs5260-travel-agent/travel-agent-repo/backend:1.0.0
   ```

---

## 3. Connecting to the Server

Once your images are stored securely on the registry, SSH into your provisioned Virtual Machine.
Use the `ssh_command` that was output by the `terraform apply` step.

From the SSH terminal of your Compute Engine instance, you don't even need to authenticate Docker manually (because we explicitly added the `gcloud auth configure-docker` step to the VM's startup script in Terraform).

You can immediately pull and run your containers:

### 1. Pull the Docker Images

```bash
docker pull asia-southeast1-docker.pkg.dev/cs5260-travel-agent/travel-agent-repo/backend:1.0.0
docker pull asia-southeast1-docker.pkg.dev/cs5260-travel-agent/travel-agent-repo/frontend:1.0.0
```

### 2. Run the Application

Start the backend container on port `8000`:
```bash
docker run -d \
  --name travel-backend \
  -p 8000:8000 \
  --restart unless-stopped \
  asia-southeast1-docker.pkg.dev/cs5260-travel-agent/travel-agent-repo/backend:1.0.0
```

Start the frontend container on port `80`:
```bash
docker run -d \
  --name travel-frontend \
  -p 80:80 \
  --restart unless-stopped \
  asia-southeast1-docker.pkg.dev/cs5260-travel-agent/travel-agent-repo/frontend:1.0.0
```

Your system is now deployed! Access your frontend at `http://34.126.173.27` from your browser.
