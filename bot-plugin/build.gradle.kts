plugins {
    `java-library`
    id("io.papermc.paperweight.userdev") version "2.0.0-beta.22"
}

group = "io.opencode.minecraft"
version = "1.0.0"

val paperVersion = "26.2.build.+"

java {
    sourceCompatibility = JavaVersion.VERSION_25
    targetCompatibility = JavaVersion.VERSION_25
}

repositories {
    mavenCentral()
    maven("https://repo.papermc.io/repository/maven-public/")
}

dependencies {
    paperweight.paperDevBundle(paperVersion)
    compileOnly("io.papermc.paper:paper-api:$paperVersion")
}

paperweight.reobfArtifactConfiguration =
    io.papermc.paperweight.userdev.ReobfArtifactConfiguration.MOJANG_PRODUCTION

tasks.jar {
    archiveBaseName.set("mc-bot-plugin")
    manifest.attributes["paper-plugin-version"] = project.version
}
