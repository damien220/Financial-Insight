"""
Base Tool Module

This module provides the abstract base class for all MCP tools.
It defines the core interface that all tools must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from core.models import ToolDefinition, ToolParameter, ToolProperty


class BaseTool(ABC):
    """
    Abstract base class for all MCP tools.
    
    All tools must inherit from this class and implement the execute method.
    The base class provides common functionality for tool definition,
    validation, and metadata management.
    """
    
    def __init__(self):
        """Initialize the base tool."""
        self._name: Optional[str] = None
        self._description: Optional[str] = None
        self._parameters: Optional[Dict[str, Any]] = None
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        Execute the tool with the given arguments.
        
        This is an abstract method that must be implemented by all concrete tools.
        
        Args:
            **kwargs: Tool-specific arguments
            
        Returns:
            Any: The result of the tool execution
            
        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError("Subclasses must implement the execute method")
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Get the tool name.
        
        Returns:
            str: The unique name of the tool
        """
        raise NotImplementedError("Subclasses must implement the get_name method")
    
    @abstractmethod
    def get_description(self) -> str:
        """
        Get the tool description.
        
        Returns:
            str: A description of what the tool does
        """
        raise NotImplementedError("Subclasses must implement the get_description method")
    
    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Get the tool's parameter schema.
        
        Returns:
            Dict[str, Any]: Schema defining the tool's parameters
        """
        raise NotImplementedError("Subclasses must implement the get_parameters_schema method")
    
    def get_definition(self) -> ToolDefinition:
        """
        Get the complete tool definition as a ToolDefinition model.
        
        This method constructs the tool definition from the tool's metadata.
        
        Returns:
            ToolDefinition: Complete tool definition including name, description, and parameters
        """
        schema = self.get_parameters_schema()
        
        # Convert schema to ToolParameter format
        properties = {}
        for prop_name, prop_info in schema.get("properties", {}).items():
            properties[prop_name] = ToolProperty(
                type=prop_info.get("type", "string"),
                description=prop_info.get("description")
            )
        
        parameters = ToolParameter(
            type=schema.get("type", "object"),
            properties=properties,
            required=schema.get("required", [])
        )
        
        return ToolDefinition(
            name=self.get_name(),
            description=self.get_description(),
            parameters=parameters
        )
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate the provided arguments against the tool's parameter schema.
        
        Args:
            arguments: Dictionary of arguments to validate
            
        Returns:
            tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        schema = self.get_parameters_schema()
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        
        # Check required parameters
        for req_param in required:
            if req_param not in arguments:
                return False, f"Missing required parameter: {req_param}"
        
        # Check parameter types (basic validation)
        for arg_name, arg_value in arguments.items():
            if arg_name not in properties:
                return False, f"Unknown parameter: {arg_name}"
            
            expected_type = properties[arg_name].get("type")
            if expected_type and not self._check_type(arg_value, expected_type):
                return False, f"Parameter '{arg_name}' has invalid type. Expected {expected_type}"
        
        return True, None
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """
        Check if a value matches the expected type.
        
        Args:
            value: The value to check
            expected_type: The expected type as a string
            
        Returns:
            bool: True if type matches, False otherwise
        """
        type_mapping = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict
        }
        
        expected_python_type = type_mapping.get(expected_type)
        if expected_python_type is None:
            return True  # Unknown type, skip validation
        
        return isinstance(value, expected_python_type)
    
    def __repr__(self) -> str:
        """String representation of the tool."""
        return f"<{self.__class__.__name__}: {self.get_name()}>"
