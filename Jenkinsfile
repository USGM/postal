pipeline {
  agent {
    node {
        label ""
        customWorkspace "${currentBuild.id}_${currentBuild.startTimeInMillis}"
    }
  }

  // using the Timestamper plugin we can add timestamps to the console log
  options {
    // disabled due to bug JENKINS-48556
    // timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '3'))
  }
  environment {
       MAIL_TO = "it+ci@usglobalmail.com"
       DOCKER_REGISTRY = 'registry.usglobalmail.com:5000'
       PATH = "${env.WORKSPACE}/.local/bin:${env.PATH}"
       COMPOSE_FILE = "docker-compose.yml"
       REPO_PRIV_KEY_FILE = credentials('REPO_PRIV_KEY_FILE')
       DOCKER_REGISTRY_AUTH = credentials('DOCKER_REGISTRY_AUTH')
       TARGET_ENV = 'test'
  }

  stages {
    stage ('Prep') {
        steps {
            sh "postal/tests/prep.sh"
        }
    }
    stage('Unit Tests') {
      steps {
        sh "echo 'Run Unit Tests'"
        sh "make"
      }
    }
  }
  post {
    always {
      sh "make dc-down"
      //junit "build/junit/*.xml"
      deleteDir()
    }
    success {
      mail to:"${env.CHANGE_AUTHOR_EMAIL}",
        cc: "${env.MAIL_TO}",
        subject: "SUCCESS: ${currentBuild.fullDisplayName}",
        body: "Build succeded, see build log here: ${env.BUILD_URL}"
    }
    failure {
      mail to:"${env.CHANGE_AUTHOR_EMAIL}",
        cc: "${env.MAIL_TO}",
        subject: "FAILURE: ${currentBuild.fullDisplayName}",
        body: "Build failed, see build log here: ${env.BUILD_URL}"
    }
  }
}
