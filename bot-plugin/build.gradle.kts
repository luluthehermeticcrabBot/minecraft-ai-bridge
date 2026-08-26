import groovy.json.JsonSlurper
import java.net.HttpURLConnection
import java.net.URI

plugins {
    `java-library`
    id("io.papermc.paperweight.userdev") version "2.0.0-beta.22"
}

group = "io.opencode.minecraft"
version = "1.0.0"

fun selectLatestStablePaperVersion(response: Map<*, *>): String {
    val versions = response["versions"] as? List<*>
        ?: error("Paper Fill API response has no versions array")
    return versions.asSequence()
        .mapNotNull { entry ->
            val version = (entry as? Map<*, *>)?.get("version") as? Map<*, *>
            version?.get("id") as? String
        }
        .firstOrNull { !it.contains('-') }
        ?: error("Paper Fill API response has no stable release")
}

fun resolveLatestPaperVersion(): String {
    val connection = URI("https://fill.papermc.io/v3/projects/paper/versions")
        .toURL()
        .openConnection() as HttpURLConnection
    connection.connectTimeout = 10_000
    connection.readTimeout = 10_000
    connection.requestMethod = "GET"
    connection.setRequestProperty("Accept", "application/json")

    return connection.inputStream.bufferedReader().use { reader ->
        val response = JsonSlurper().parseText(reader.readText()) as Map<*, *>
        selectLatestStablePaperVersion(response)
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
tasks.register("testPaperVersionResolver") {
    doLast {
        val orderedVersions = mapOf(
            "versions" to listOf(
                mapOf("version" to mapOf("id" to "26.3-rc-1")),
                mapOf("version" to mapOf("id" to "26.2")),
                mapOf("version" to mapOf("id" to "26.1.2")),
            ),
        )
        check(selectLatestStablePaperVersion(orderedVersions) == "26.2")

        val noStableRelease = mapOf(
            "versions" to listOf(
                mapOf("version" to mapOf("id" to "26.3-rc-1")),
            ),
        )
        check(
            runCatching { selectLatestStablePaperVersion(noStableRelease) }
                .exceptionOrNull()
                ?.message == "Paper Fill API response has no stable release",
        )
    }
}

tasks.named("check") {
    dependsOn("testPaperVersionResolver")
}
