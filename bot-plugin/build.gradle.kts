import groovy.json.JsonSlurper
import java.net.HttpURLConnection
import java.net.URI

plugins {
    `java-library`
    id("io.papermc.paperweight.userdev") version "2.0.0-beta.22"
}

group = "io.opencode.minecraft"
version = "1.0.0"

fun resolveLatestPaperVersion(): String {
    val connection = URI("https://fill.papermc.io/v3/projects/paper")
        .toURL()
        .openConnection() as HttpURLConnection
    connection.connectTimeout = 10_000
    connection.readTimeout = 10_000
    connection.requestMethod = "GET"
    connection.setRequestProperty("Accept", "application/json")

    return connection.inputStream.bufferedReader().use { reader ->
        val versions = (JsonSlurper().parseText(reader.readText()) as Map<*, *>)["versions"]
            as Map<*, *>
        val latestReleaseGroup = versions.values.first() as List<*>
        latestReleaseGroup.first { it is String && !it.contains('-') } as String
    }
}

val paperMinecraftVersion = providers.gradleProperty("paperMinecraftVersion")
    .orNull
    ?: resolveLatestPaperVersion()
val paperVersion = "$paperMinecraftVersion.build.+"
logger.lifecycle("Using latest Paper dev bundle: $paperVersion")

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
