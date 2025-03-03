#!/usr/bin/env python3
import os
import re
import json
import sys
import argparse
import logging
from ruamel.yaml import YAML, YAMLError
from pathlib import Path
from typing import Dict, Any, List, Optional
from jsonschema import validate, ValidationError, Draft7Validator
from dataclasses import dataclass
from termcolor import colored

PARTIAL_SCHEMA_COMMENT = "# yaml-language-server: $schema={schema_path}/kong-service-partial-schema.json"
MERGED_SCHEMA_COMMENT = "# yaml-language-server: $schema={schema_path}/kong-service-merged-schema.json"

# Configure logging
def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

logger = logging.getLogger(__name__)

@dataclass
class ValidationErrorInfo:
    """Store validation error information"""
    file_path: Path
    error_path: str
    error_message: str
    
    def __str__(self) -> str:
        return f"{self.file_path}:\n  Path: {self.error_path}\n  Error: {self.error_message}"

# Helper functions to colorize the output
red = lambda text: colored(text, "red")
green = lambda text: colored(text, "green")
bold = lambda text: colored(text, attrs=["bold"])

class ValidationErrors:
    """Collect and manage validation errors"""
    def __init__(self):
        self.errors: List[ValidationErrorInfo] = [] # Track schema validation errors
        self.yaml_errors: Dict[Path, str] = {}  # Track YAML parsing errors
    
    def add_error(self, file_path: Path, error_path: str, error_message: str):
        self.errors.append(ValidationErrorInfo(file_path, error_path, error_message))
    
    def add_yaml_error(self, file_path: Path, error_message: str):
        self.yaml_errors[file_path] = error_message
    
    def has_errors(self) -> bool:
        return bool(self.errors or self.yaml_errors)
    
    def print_summary(self):
        if not self.has_errors():
            logger.info(green("✓ All files are valid"))
            return
            
        summary = [f"\n{red('❌ Validation Errors Summary:')}", "=" * 80]
        
        # Print YAML parsing errors first
        if self.yaml_errors:
            summary.extend([f"\n{bold('YAML Parsing Errors:')}", "-" * 80])
            for file_path, error in self.yaml_errors.items():
                summary.extend([
                    f"\nFile: {bold(file_path)}",
                    f"Error: {red(error)}",
                    "Hint: Please check the YAML syntax in this file"
                ])
        
        # Print schema validation errors
        if self.errors:
            if self.yaml_errors:
                summary.extend([f"\n{bold('Schema Validation Errors:')}", "-" * 80])
            
            summary.append(f"\nTotal validation errors: {red(str(len(self.errors)))}")
            
            # Group errors by file
            errors_by_file: Dict[Path, List[ValidationErrorInfo]] = {}
            for error in self.errors:
                if error.file_path not in errors_by_file:
                    errors_by_file[error.file_path] = []
                errors_by_file[error.file_path].append(error)
            
            # Print errors grouped by file
            for file_path, errors in errors_by_file.items():
                summary.append(f"\nFile: {bold(file_path)}")
                for i, error in enumerate(errors, 1):
                    summary.extend([
                        f"  {i}. Path: {bold(error.error_path)}",
                        f"     Error: {red(error.error_message)}"
                    ])
                summary.append("  Hint: Please check the Kong service configuration schema for valid values")
        
        summary.append("=" * 80)
        logger.error("\n".join(summary))

# Global validation errors collector
validation_errors = ValidationErrors()

def load_schema(schema_path: Path) -> Dict[str, Any]:
    """Load and parse a JSON schema file."""
    try:
        with schema_path.open('r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in schema {schema_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading schema {schema_path}: {e}")
        raise

yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.preserve_quotes = True
yaml.width = 120

def merge_named_lists(base_list: List[Dict[str, Any]], override_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge two lists of dictionaries based on the 'name' field."""
    # Create a map of name -> item for base list
    merged_map = {item['name']: item for item in base_list if 'name' in item}
    
    # Update or add items from override list
    for override_item in override_list:
        if 'name' in override_item:
            name = override_item['name']
            if name in merged_map:
                # If item exists in base, merge it
                merged_map[name] = deep_merge(merged_map[name], override_item)
            else:
                # If item doesn't exist, add it
                merged_map[name] = override_item
                
    # Convert back to list, preserving order from base list and appending new items
    result = []
    seen_names = set()
    
    # First, add items in the order they appear in base_list
    for item in base_list:
        if 'name' in item:
            name = item['name']
            result.append(merged_map[name])
            seen_names.add(name)
    
    # Then add any new items from override_list that weren't in base_list
    for item in override_list:
        if 'name' in item and item['name'] not in seen_names:
            result.append(item)
            
    return result

def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    merged = base.copy()
    
    for key, value in override.items():
        if (
            key in merged 
            and isinstance(merged[key], dict) 
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        elif (
            key in merged 
            and isinstance(merged[key], list) 
            and isinstance(value, list)
            and merged[key] 
            and value 
            and isinstance(merged[key][0], dict)
            and isinstance(value[0], dict)
            and 'name' in merged[key][0]
            and 'name' in value[0]
        ):
            # For lists of named dictionaries (like plugins or routes), merge by name
            merged[key] = merge_named_lists(merged[key], value)
        else:
            merged[key] = value
            
    return merged

def load_yaml(file_path: Path) -> Optional[Dict[str, Any]]:
    """Load YAML file with error handling, preserving comments and formatting."""
    try:
        with file_path.open('r') as f:
            content = f.read()
            # Remove only the schema reference comment if it exists
            content = re.sub(r'#\s*yaml-language-server:[^\n]*\n+', '', content)
            data = yaml.load(content)
            if data is None:
                msg = "Empty YAML file"
                validation_errors.add_yaml_error(file_path, msg)
                logger.error(f"{msg}: {file_path}")
                return None
            return data
    except YAMLError as e:
        msg = f"Invalid YAML: {e}"
        validation_errors.add_yaml_error(file_path, str(e))
        logger.error(f"{msg} in {file_path}")
        return None
    except Exception as e:
        msg = f"Error loading file: {e}"
        validation_errors.add_yaml_error(file_path, str(e))
        logger.error(f"{msg}: {file_path}")
        return None

def validate_yaml(data: Dict[str, Any], schema: Dict[str, Any], file_path: Path) -> bool:
    """Validate YAML data against JSON schema."""
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(data))
    
    if not errors:
        logger.debug(f"✓ {file_path} is valid")
        return True
    
    # Add all errors found
    for error in errors:
        error_path = ' -> '.join(str(p) for p in error.path)
        validation_errors.add_error(file_path, error_path, error.message)
    
    logger.error(f"✗ {file_path} has {len(errors)} validation errors")
    return False

def get_schema_relative_path(schema_dir: Path, yaml_file: Path) -> str:
    """
    Calculate the relative path from YAML file to schema directory.
    This ensures schema references work regardless of file locations.
    """
    try:
        # Get relative path from YAML file's parent dir to schema dir
        rel_path = os.path.relpath(schema_dir, yaml_file.parent)
        return rel_path
    except ValueError:
        # Fallback to absolute path if files are on different drives
        return str(schema_dir)

def check_schema_comment(file_path: Path, expected_comment: str) -> bool:
    """Check if file already has the correct schema comment."""
    try:
        with file_path.open('r') as f:
            first_line = f.readline().strip()
            return first_line == expected_comment
    except Exception as e:
        logger.debug(f"Error checking schema comment in {file_path}: {e}")
        return False

def save_yaml(file_path: Path, data: Dict[str, Any], schema_comment_template: str, schema: Dict[str, Any], schema_dir: Path) -> bool:
    """Save YAML file with schema reference and validate against schema."""
    try:
        # Validate before saving
        if not validate_yaml(data, schema, file_path):
            logger.warning(f"Invalid YAML in {file_path}")
            return False

        # Calculate relative path for schema reference
        schema_path = get_schema_relative_path(schema_dir, file_path)
        schema_comment = schema_comment_template.format(schema_path=schema_path)

        # Check if file already has the correct schema comment
        if check_schema_comment(file_path, schema_comment):
            logger.debug(f"Schema comment already up to date in {file_path}")
            return True

        # Save only if validation passed and schema comment needs updating
        with file_path.open('w') as f:
            f.write(f"{schema_comment}\n\n")
            yaml.dump(data, f)
        logger.info(f"Updated schema comment in {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")
        return False

def process_yaml_files(service_dir: Path, partial_schema: Dict[str, Any], merged_schema: Dict[str, Any], schema_dir: Path, generate_merged: bool = False) -> None:
    """
    Process YAML files in a service directory.
    
    Args:
        service_dir: Directory containing YAML files
        partial_schema: Schema for validating individual YAML files
        merged_schema: Schema for validating merged configurations
        schema_dir: Directory containing schema files
        generate_merged: Whether to generate merged YAML files
    """
    # First, look for base values.yaml
    base_file = service_dir / "values.yaml"
    if not base_file.exists():
        logger.warning(f"No values.yaml found in {service_dir}")
        return
        
    # Load base configuration
    base_config = load_yaml(base_file)
    if base_config is None:
        return
        
    # Validate and update base file with schema reference
    base_valid = validate_yaml(base_config, partial_schema, base_file)
    if base_valid:
        save_yaml(base_file, base_config, PARTIAL_SCHEMA_COMMENT, partial_schema, schema_dir)
    
    # Process all values-*.yaml files
    for yaml_file in service_dir.glob("values-*.yaml"):
        # Skip already merged files
        if yaml_file.name.endswith("-merged.yaml"):
            continue
            
        logger.info(f"\nProcessing {yaml_file}")
        
        # Load override configuration
        override_config = load_yaml(yaml_file)
        if override_config is None:
            continue
        
        # Validate and add schema reference to original file
        override_valid = validate_yaml(override_config, partial_schema, yaml_file)
        if override_valid:
            save_yaml(yaml_file, override_config, PARTIAL_SCHEMA_COMMENT, partial_schema, schema_dir)
        
        # Only validate merged configuration if base and override are valid
        if base_valid and override_valid:
            # Merge configurations
            merged_config = deep_merge(base_config, override_config)
            
            if generate_merged:
                # Generate merged file name and save if requested
                merged_file = yaml_file.parent / f"{yaml_file.stem}-merged.yaml"
                if validate_yaml(merged_config, merged_schema, merged_file):
                    save_yaml(merged_file, merged_config, MERGED_SCHEMA_COMMENT, merged_schema, schema_dir)
            else:
                # Just validate using virtual path
                virtual_merged_path = yaml_file.parent / f"{yaml_file.stem}-merged"
                validate_yaml(merged_config, merged_schema, virtual_merged_path)

def process_services_directory(services_dir: Path, partial_schema: Dict[str, Any], merged_schema: Dict[str, Any], schema_dir: Path, generate_merged: bool = False) -> None:
    """Process all service directories."""
    for service_dir in services_dir.iterdir():
        if not service_dir.is_dir():
            continue
            
        logger.info(f"\nProcessing service directory: {service_dir}")
        process_yaml_files(service_dir, partial_schema, merged_schema, schema_dir, generate_merged)

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate and process Kong service YAML configurations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--generate-merged",
        action="store_true",
        help="Generate merged YAML files for debugging"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()

    return args

def main():
    args = parse_arguments()
    setup_logging(args.verbose)
    
    # Try to find Kong config files in the current directory and its subdirectories
    services_dir = Path.cwd()
    if not (services_dir / "kong-config" / "services").exists():
        # Look for kong-config/services in current directory or parent directories
        current = services_dir
        while current != current.parent:
            kong_services = current / "kong-config" / "services"
            if kong_services.exists():
                services_dir = kong_services
                break
            current = current.parent
    else:
        services_dir = services_dir / "kong-config" / "services"
    
    if not services_dir.exists():
        logger.error(f"Could not find Kong services directory in {services_dir} or its parent directories")
        logger.error("Please run this script from a directory containing kong-config/services")
        sys.exit(1)

    # Try to find Kong schema files in the current directory and its subdirectories
    schemas_dir = Path.cwd()
    if not (schemas_dir / "kong-config" / "schemas").exists():
        # Look for kong-config/schemas in current directory or parent directories
        current = schemas_dir
        while current != current.parent:
            kong_schemas = current / "kong-config" / "schemas"
            if kong_schemas.exists():
                schemas_dir = kong_schemas
                break
            current = current.parent
    else:
        schemas_dir = schemas_dir / "kong-config" / "schemas"
    
    if not schemas_dir.exists():
        logger.error(f"Could not find Kong schemas directory in {schemas_dir} or its parent directories")
        logger.error("Please ensure kong-config/schemas exists in your repository")
        sys.exit(1)

    logger.info(f"Using services directory: {services_dir}")
    logger.info(f"Using schemas directory: {schemas_dir}")

    # Load schemas
    try:
        partial_schema = load_schema(schemas_dir / "kong-service-partial-schema.json")
        merged_schema = load_schema(schemas_dir / "kong-service-merged-schema.json")
    except Exception as e:
        logger.error(f"Failed to load schemas: {e}")
        sys.exit(1)
        
    logger.info(f"Processing YAML files in {services_dir}")
    if args.generate_merged:
        logger.info("Will generate merged YAML files for debugging")
        
    process_services_directory(services_dir, partial_schema, merged_schema, schemas_dir, args.generate_merged)

    validation_errors.print_summary()
    if validation_errors.has_errors():
        sys.exit(1)
        
    logger.info("\nDone!")

if __name__ == "__main__":
    main() 