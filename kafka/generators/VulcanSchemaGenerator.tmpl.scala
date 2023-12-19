package kp_pre_commit_hooks

import org.apache.avro.Schema
import __SCHEMA_PACKAGE__.__SCHEMA_CLASS_NAME__

import vulcan._

def schemaToString(schema: Schema): String = ujson.write(ujson.read(schema.toString()), indent = 4)

def writeSchema(schema: Schema, schemaFilename: String) = {
  Console.println(s"Writing ${schema.getName} schema to ${schemaFilename}")
  val schemaFilePath = os.Path(schemaFilename, os.pwd)
  os.write.over(schemaFilePath, schemaToString(schema), createFolders = true)
}

@main def generateSchemaFile(schemaFilename: String) = {

  val generatedSchema = summon[Codec[__SCHEMA_CLASS_NAME__]].schema

  generatedSchema match {
    case Right(schema) => writeSchema(schema, schemaFilename)
    case Left(error) => {
      System.err.println(s"ERROR: Couldn't generate the schema because of the following error: ${error.toString}")
      System.exit(2)
    }
  }
}
