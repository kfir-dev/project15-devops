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

        stage('Python environment') {
            steps {
                dir('application') {
                    sh '''
                        set -eu
                        python3 -m venv .venv
                        .venv/bin/python -m pip install -r requirements-dev.txt
                    '''
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
    }

    post {
        always {
            junit testResults: 'application/reports/pytest.xml',
                  allowEmptyResults: true
            archiveArtifacts artifacts: 'application/reports/coverage.xml',
                             allowEmptyArchive: true
        }
    }
}
