"""
Tool Loader Module

This module provides functionality for dynamically discovering, loading,
and managing tool instances within the MCP server.
"""

import os
import importlib
import inspect
from typing import Dict, List, Optional, Type
from pathlib import Path
from tools.base import BaseTool
from core.models import ToolDefinition


class ToolLoader:
    """
    Manages the discovery, loading, and registration of tools.
    
    The ToolLoader automatically discovers tool classes from specified directories,
    instantiates them, and provides access to tool instances and their definitions.
    """
    
    def __init__(self, tools_directory: Optional[str] = None):
        """
        Initialize the ToolLoader.
        
        Args:
            tools_directory: Path to the directory containing tool modules.
                           If None, uses the tools/ directory relative to this file.
        """
        self._tools: Dict[str, BaseTool] = {}
        self._tools_directory = tools_directory or self._get_default_tools_directory()
    
    def _get_default_tools_directory(self) -> str:
        """
        Get the default tools directory path.
        
        Returns:
            str: Absolute path to the tools directory
        """
        current_file = Path(__file__).resolve()
        tools_dir = current_file.parent
        return str(tools_dir)
    
    def load_tools(self, tool_directories: Optional[List[str]] = None) -> int:
        """
        Discover and load all tools from specified directories.
        
        This method scans the specified directories for Python modules containing
        BaseTool subclasses and instantiates them.
        
        Args:
            tool_directories: List of directory names within the tools directory to scan.
                            If None, scans all subdirectories.
        
        Returns:
            int: Number of tools successfully loaded
        """
        if tool_directories is None:
            tool_directories = self._discover_tool_directories()
        
        loaded_count = 0
        tools_path = Path(self._tools_directory)
        
        for tool_dir in tool_directories:
            dir_path = tools_path / tool_dir
            if not dir_path.is_dir():
                continue
            
            # Look for Python files in the directory
            for py_file in dir_path.glob("*_tool.py"):
                try:
                    module_name = f"tools.{tool_dir}.{py_file.stem}"
                    tool_instance = self._load_tool_from_module(module_name)
                    
                    if tool_instance:
                        tool_name = tool_instance.get_name()
                        self._tools[tool_name] = tool_instance
                        loaded_count += 1
                        
                except Exception as e:
                    print(f"Error loading tool from {py_file}: {e}")
                    continue
        
        return loaded_count
    
    def _discover_tool_directories(self) -> List[str]:
        """
        Discover all subdirectories in the tools directory.
        
        Returns:
            List[str]: List of directory names
        """
        tools_path = Path(self._tools_directory)
        directories = []
        
        for item in tools_path.iterdir():
            if item.is_dir() and not item.name.startswith("__"):
                directories.append(item.name)
        
        return directories
    
    def _load_tool_from_module(self, module_name: str) -> Optional[BaseTool]:
        """
        Load a tool class from a module and instantiate it.
        
        Args:
            module_name: Fully qualified module name
            
        Returns:
            Optional[BaseTool]: Instantiated tool or None if not found
        """
        try:
            module = importlib.import_module(module_name)
            
            # Find all BaseTool subclasses in the module
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, BaseTool) and 
                    obj is not BaseTool and 
                    obj.__module__ == module_name):
                    return obj()
            
            return None
            
        except Exception as e:
            raise ImportError(f"Failed to load module {module_name}: {e}")
    
    def register_tool(self, tool: BaseTool) -> None:
        """
        Manually register a tool instance.
        
        Args:
            tool: An instance of a BaseTool subclass
            
        Raises:
            ValueError: If tool is not a BaseTool instance
        """
        if not isinstance(tool, BaseTool):
            raise ValueError("Tool must be an instance of BaseTool")
        
        tool_name = tool.get_name()
        self._tools[tool_name] = tool
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        Get a tool instance by name.
        
        Args:
            tool_name: Name of the tool to retrieve
            
        Returns:
            Optional[BaseTool]: Tool instance or None if not found
        """
        return self._tools.get(tool_name)
    
    def list_tools(self) -> List[str]:
        """
        Get a list of all registered tool names.
        
        Returns:
            List[str]: List of tool names
        """
        return list(self._tools.keys())
    
    def get_tool_definitions(self) -> List[ToolDefinition]:
        """
        Get definitions for all registered tools.
        
        Returns:
            List[ToolDefinition]: List of tool definitions
        """
        return [tool.get_definition() for tool in self._tools.values()]
    
    def get_tool_count(self) -> int:
        """
        Get the number of registered tools.
        
        Returns:
            int: Number of tools
        """
        return len(self._tools)
    
    def clear_tools(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
    
    async def execute_tool(self, tool_name: str, arguments: Dict) -> tuple[bool, any]:
        """
        Execute a tool by name with the provided arguments.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Dictionary of arguments for the tool
            
        Returns:
            tuple[bool, any]: (success, result_or_error_message)
        """
        tool = self.get_tool(tool_name)
        
        if tool is None:
            return False, f"Tool '{tool_name}' not found"
        
        # Validate arguments
        is_valid, error_msg = tool.validate_arguments(arguments)
        if not is_valid:
            return False, f"Invalid arguments: {error_msg}"
        
        # Execute the tool
        try:
            result = await tool.execute(**arguments)
            return True, result
        except Exception as e:
            return False, f"Tool execution failed: {str(e)}"
    
    def __repr__(self) -> str:
        """String representation of the loader."""
        return f"<ToolLoader: {len(self._tools)} tools loaded>"
