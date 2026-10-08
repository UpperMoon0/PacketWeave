from pathlib import Path
import shutil, json
ROOT=Path(__file__).resolve().parents[1]
def write(name, text):
    p=ROOT/name
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text.strip().replace("DOLLAR_",chr(36))+"\n",encoding="utf-8",newline="\n")
    print("created",name)
def fmt(text,**kwargs):
    for k,v in kwargs.items():text=text.replace("ZZ"+k+"ZZ",str(v))
    return text

targets=[
("fabric","1.16.5",8,"9.7.1"),("forge","1.16.5",8,"8.8"),
("fabric","1.20.1",17,"9.7.1"),("forge","1.20.1",17,"8.8"),
("fabric","1.21.1",21,"9.7.1"),("neoforge","1.21.1",21,"9.2.1"),
("fabric","26.1.2",25,"9.7.1"),("neoforge","26.1.2",25,"9.2.1")]
versions={
"1.16.5":{"loader":"0.19.5","forge":"36.2.42"},
"1.20.1":{"loader":"0.17.2","forge":"47.4.21"},
"1.21.1":{"loader":"0.17.2","neo":"21.1.201"},
"26.1.2":{"loader":"0.19.5","neo":"26.1.2.114"}}
uppers={"1.16.5":"1.17","1.20.1":"1.21","1.21.1":"1.22","26.1.2":"26.2"}
settings=r"""
pluginManagement {
    repositories {
        ZZMAVENZZ
        mavenCentral()
        gradlePluginPortal()
    }
}
plugins { id 'org.gradle.toolchains.foojay-resolver-convention' version 'ZZFOOJAYZZ' }
rootProject.name = 'packetweave-ZZTARGETZZ'
"""
fabric=r"""
plugins {
    id 'ZZLOOMZZ' version '1.17.9'
    id 'maven-publish'
}
group = 'com.nstut'
version = mod_version
base { archivesName = 'packetweave-ZZTARGETZZ' }
java {
    toolchain.languageVersion = JavaLanguageVersion.of(ZZJAVAZZ)
    sourceCompatibility = JavaVersion.toVersion(ZZJAVAZZ)
    targetCompatibility = JavaVersion.toVersion(ZZJAVAZZ)
    withSourcesJar()
}
sourceSets.main.java.srcDir file('../../core/src/main/java')
dependencies {
    minecraft "com.mojang:minecraft:DOLLAR_{minecraft_version}"
    ZZMAPPINGZZ
    ZZDEPZZ "net.fabricmc:fabric-loader:DOLLAR_{loader_version}"
}
processResources {
    inputs.property 'mod_version', version
    filesMatching('fabric.mod.json') { expand mod_version: version }
}
tasks.withType(JavaCompile).configureEach { if (ZZJAVAZZ >= 9) options.release = ZZJAVAZZ; options.encoding = 'UTF-8' }
publishing { publications { mavenJava(MavenPublication) { artifactId = base.archivesName.get(); from components.java } } }
"""
forge=r"""
plugins {
    id 'java-library'
    id 'net.minecraftforge.gradle' version '[6.0,6.2)'
    id 'maven-publish'
}
group = 'com.nstut'
version = mod_version
base { archivesName = 'packetweave-ZZTARGETZZ' }
java { toolchain.languageVersion = JavaLanguageVersion.of(ZZJAVAZZ); withSourcesJar() }
sourceSets.main.java.srcDir file('../../core/src/main/java')
minecraft {
    mappings channel: 'official', version: minecraft_version
    copyIdeResources = true
    runs {
        client { workingDirectory project.file('run'); mods { packetweave { source sourceSets.main } } }
        server { workingDirectory project.file('run'); args '--nogui'; mods { packetweave { source sourceSets.main } } }
    }
}
dependencies { minecraft "net.minecraftforge:forge:DOLLAR_{minecraft_version}-DOLLAR_{forge_version}" }
processResources {
    def params = [mod_version: version]
    inputs.properties params
    filesMatching('META-INF/mods.toml') { expand params }
}
tasks.withType(JavaCompile).configureEach { if (ZZJAVAZZ >= 9) options.release = ZZJAVAZZ; options.encoding = 'UTF-8' }
jar {
    manifest { attributes 'Specification-Title': 'packetweave', 'Implementation-Version': version }
    finalizedBy 'reobfJar'
}
publishing { publications { mavenJava(MavenPublication) { artifactId = base.archivesName.get(); from components.java } } }
"""
neo=r"""
plugins {
    id 'java-library'
    id 'maven-publish'
    id 'net.neoforged.moddev' version '2.0.148'
}
group = 'com.nstut'
version = mod_version
base { archivesName = 'packetweave-ZZTARGETZZ' }
java { toolchain.languageVersion = JavaLanguageVersion.of(ZZJAVAZZ); withSourcesJar() }
sourceSets.main.java.srcDir file('../../core/src/main/java')
neoForge {
    version = project.neo_version
    runs { client { client() }; server { server(); programArgument '--nogui' } }
    mods { packetweave { sourceSet(sourceSets.main) } }
}
processResources {
    def params = [mod_version: version]
    inputs.properties params
    filesMatching('META-INF/neoforge.mods.toml') { expand params }
}
tasks.withType(JavaCompile).configureEach { if (ZZJAVAZZ >= 9) options.release = ZZJAVAZZ; options.encoding = 'UTF-8' }
publishing { publications { mavenJava(MavenPublication) { artifactId = base.archivesName.get(); from components.java } } }
"""
forge_toml=r"""
modLoader="javafml"
loaderVersion="[ZZMAJORZZ,)"
license="MIT"
[[mods]]
modId="packetweave"
version="DOLLAR_{mod_version}"
displayName="PacketWeave"
authors="NsTut"
description='''A safe and bounded binary transfer engine for Minecraft mods.'''
[[dependencies.packetweave]]
modId="minecraft"
mandatory=true
versionRange="[ZZMCZZ,ZZUPZZ)"
ordering="NONE"
side="BOTH"
"""
neo_toml=r"""
modLoader="javafml"
loaderVersion="[1,)"
license="MIT"
[[mods]]
modId="packetweave"
version="DOLLAR_{mod_version}"
displayName="PacketWeave"
authors="NsTut"
description='''A safe and bounded binary transfer engine for Minecraft mods.'''
[[dependencies.packetweave]]
modId="minecraft"
type="required"
versionRange="[ZZMCZZ,ZZUPZZ)"
ordering="NONE"
side="BOTH"
"""
entry_fabric=r"""
package com.nstut.packetweave.fabric;
import net.fabricmc.api.ModInitializer;
/** The loader adapter does not depend on Fabric API or Architectury. */
public final class PacketWeaveFabric implements ModInitializer {
    public static final String MOD_ID = "packetweave";
    @Override public void onInitialize() {
        // Packet codecs are not registered by the initial core/scaffolding release.
    }
}
"""
entry_forge=r"""
package com.nstut.packetweave.forge;
import net.minecraftforge.fml.common.Mod;
@Mod("packetweave")
public final class PacketWeaveForge {
    public PacketWeaveForge() { }
}
"""
entry_neo=r"""
package com.nstut.packetweave.neoforge;
import net.neoforged.fml.common.Mod;
@Mod("packetweave")
public final class PacketWeaveNeoForge {
    public PacketWeaveNeoForge() { }
}
"""
src=Path(r"D:\Workspaces\Minecraft Projects\MC Mods\Simply-Speakers")
for mod, mc, java, gradle in targets:
    target=mod+"-"+mc; path="targets/"+target
    props=["org.gradle.jvmargs=-Xmx2G","org.gradle.parallel=true",
           "org.gradle.caching=true","org.gradle.configuration-cache=false",
           "mod_version=0.1.0","minecraft_version="+mc]
    if mod=="fabric":
        props.append("loader_version="+versions[mc]["loader"])
        write(path+"/build.gradle", fmt(fabric,TARGET=target,JAVA=java,
              LOOM="net.fabricmc.fabric-loom" if mc=="26.1.2" else "net.fabricmc.fabric-loom-remap",
              MAPPING="" if mc=="26.1.2" else "mappings loom.officialMojangMappings()",
              DEP="implementation" if mc=="26.1.2" else "modImplementation"))
        info={"schemaVersion":1,"id":"packetweave","version":"DOLLAR_{mod_version}",
              "name":"PacketWeave","description":"Secure, bounded data transfers for Minecraft mods.",
              "license":"MIT","environment":"*",
              "entrypoints":{"main":["com.nstut.packetweave.fabric.PacketWeaveFabric"]},
              "depends":{"fabricloader":">=0.19.5" if mc=="26.1.2" else ">=0.16.0",
                         "minecraft":mc,"java":">="+str(java)}}
        write(path+"/src/main/resources/fabric.mod.json", json.dumps(info,indent=2))
        write(path+"/src/main/java/com/nstut/packetweave/fabric/PacketWeaveFabric.java",entry_fabric)
        maven="maven { url = 'https://maven.fabricmc.net/' }"
    elif mod=="forge":
        props+=["forge_version="+versions[mc]["forge"]]
        write(path+"/build.gradle",fmt(forge,TARGET=target,JAVA=java))
        write(path+"/src/main/resources/META-INF/mods.toml",
            fmt(forge_toml,MAJOR="36" if mc=="1.16.5" else "47",MC=mc,UP=uppers[mc]))
        write(path+"/src/main/java/com/nstut/packetweave/forge/PacketWeaveForge.java",entry_forge)
        maven="maven { url = 'https://maven.minecraftforge.net/' }"
    else:
        props+=["neo_version="+versions[mc]["neo"]]
        write(path+"/build.gradle",fmt(neo,TARGET=target,JAVA=java))
        write(path+"/src/main/resources/META-INF/neoforge.mods.toml",
              fmt(neo_toml,MC=mc,UP=uppers[mc]))
        write(path+"/src/main/java/com/nstut/packetweave/neoforge/PacketWeaveNeoForge.java",entry_neo)
        maven="maven { url = 'https://maven.neoforged.net/releases' }"
    write(path+"/settings.gradle",fmt(settings,TARGET=target,MAVEN=maven,
          FOOJAY="0.9.0" if mod=="forge" else "1.0.0"))
    write(path+"/gradle.properties","\n".join(props))
    write(path+"/gradle/wrapper/gradle-wrapper.properties",fmt(r"""
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-ZZGRADLEZZ-bin.zip
networkTimeout=30000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""",GRADLE=gradle))
    for f in ["gradlew","gradlew.bat","gradle/wrapper/gradle-wrapper.jar"]:
        dest=ROOT/path/f
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src/f,dest)
        if f=="gradlew":dest.chmod(0o755)
for f in ["gradlew","gradlew.bat","gradle/wrapper/gradle-wrapper.jar"]:
    dest=ROOT/f; dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src/f,dest)
    if f=="gradlew":dest.chmod(0o755)
write("gradle/wrapper/gradle-wrapper.properties",r"""
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14-bin.zip
networkTimeout=30000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")
print("TOTAL_TARGETS="+str(len(targets)))
