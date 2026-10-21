pipeline {
    agent { label 'project15-wsl' }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timestamps()
    }

    stages {
        stage('Checkout') {
            steps {
                deleteDir()
                dir('devops') {
                    checkout scm
                }
                dir('application') {
                    git branch: 'main',
                        credentialsId: 'github-project15-read',
                        url: 'https://github.com/kfir-dev/project15-app.git'
                }
            }
        }

        stage('GitLeaks: both repositories') {
            steps {
                dir('devops') {
                    sh 'bash ci/scan-secrets.sh . ../application'
                }
            }
        }

        stage('Helm and Checkov') {
            steps {
                dir('devops') {
                    sh 'bash ci/scan-kubernetes.sh ../application/reports'
                }
            }
        }

        stage('Python environment') {
            steps {
                dir('application') {
                    sh '''
                        set -eu
                        python3 -m venv .venv
                        .venv/bin/python -m pip install --upgrade pip==26.2.1
                        .venv/bin/python -m pip install -r requirements-dev.txt
                    '''
                }
            }
        }

        stage('Python SCA: pip-audit') {
            steps {
                dir('devops') {
                    sh 'bash ci/scan-python-sca.sh ../application'
                }
            }
        }

        stage('Lint') {
            steps {
                dir('application') {
                    sh '.venv/bin/python -m flake8 app tests run.py'
                }
            }
        }

        stage('Tests and coverage') {
            steps {
                dir('application') {
                    sh '''
                        set -eu
                        mkdir -p reports
                        printf '[run]\\nrelative_files = True\\n' > reports/coverage.ini
                        COVERAGE_RCFILE=reports/coverage.ini \
                        .venv/bin/python -m pytest -q \
                            --junitxml=reports/pytest.xml \
                            --cov=app --cov=run --cov-branch \
                            --cov-report=xml:reports/coverage.xml \
                            --cov-report=term
                    '''
                }
            }
        }

        stage('SonarQube and Quality Gate') {
            steps {
                script {
                    def scannerHome = tool 'SonarScannerCLI'
                    withEnv(["SCANNER_HOME=${scannerHome}"]) {
                        withSonarQubeEnv(
                            installationName: 'SonarQubeLocal',
                            credentialsId: 'sonar-project15-token'
                        ) {
                            dir('application') {
                                sh '''
                                    set +x
                                    set -eu
                                    export SONAR_TOKEN="$SONAR_AUTH_TOKEN"
                                    "$SCANNER_HOME/bin/sonar-scanner" \
                                        -Dsonar.host.url=http://localhost:9000 \
                                        -Dsonar.projectKey=project15-app \
                                        -Dsonar.sources=app,run.py \
                                        -Dsonar.tests=tests \
                                        -Dsonar.sourceEncoding=UTF-8 \
                                        -Dsonar.python.coverage.reportPaths=reports/coverage.xml \
                                        -Dsonar.qualitygate.wait=true \
                                        -Dsonar.qualitygate.timeout=300
                                '''
                            }
                        }
                    }
                }
            }
        }

        stage('Build application image') {
            steps {
                dir('application') {
                    sh 'docker build --pull --label "org.opencontainers.image.source=https://github.com/kfir-dev/project15-app" --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" -t "project15-app:jenkins-$BUILD_NUMBER" .'
                }
            }
        }

        stage('Generate SBOM') {
            steps {
                dir('devops') {
                    sh 'bash ci/generate-sbom.sh "project15-app:jenkins-$BUILD_NUMBER" ../application/reports'
                }
            }
        }

        stage('Grype SBOM gate') {
            steps {
                dir('devops') {
                    sh 'bash ci/scan-sbom.sh ../application/reports'
                }
            }
        }

        stage('Trivy CRITICAL gate') {
            steps {
                dir('devops') {
                    sh 'bash ci/scan-image.sh "project15-app:jenkins-$BUILD_NUMBER" ../application/reports'
                }
            }
        }

        stage('Publish image to GHCR') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'ghcr-project15-push',
                    usernameVariable: 'GHCR_USERNAME',
                    passwordVariable: 'GHCR_TOKEN'
                )]) {
                    dir('devops') {
                        sh '''
                            set +x
                            set -eu
                            python3 ci/publish-image.py                                 "project15-app:jenkins-$BUILD_NUMBER"                                 ../application/reports                                 "$(git -C ../application rev-parse HEAD)"                                 "$BUILD_NUMBER"
                        '''
                    }
                }
            }
        }

        stage('Deploy to Minikube') {
            steps {
                dir('devops') {
                    sh 'python3 ci/deploy-minikube.py ../application/reports --execute'
                }
            }
        }

        stage('Post-deployment API tests') {
            steps {
                dir('devops') {
                    sh 'python3 ci/test-api.py ../application/reports'
                }
            }
        }

        stage('Post-deployment ZAP passive scan') {
            steps {
                dir('devops') {
                    sh 'python3 ci/scan-api.py ../application/reports'
                }
            }
        }
    }

    post {
        always {
            junit testResults: 'application/reports/pytest.xml,application/reports/newman.xml',
                  allowEmptyResults: true
            archiveArtifacts artifacts: 'application/reports/pip-audit.json,application/reports/coverage.xml,application/reports/scan-report.json,application/reports/sbom.json,application/reports/grype-report.json,application/reports/image-reference.txt,application/reports/image-publication.json,application/reports/checkov-report.json,application/reports/newman.xml,application/reports/deployment.json,application/reports/zap-report.json,application/reports/zap-report.html,application/reports/zap-coverage.json,application/reports/zap-summary.json',
                             allowEmptyArchive: true
        }
    }
}
