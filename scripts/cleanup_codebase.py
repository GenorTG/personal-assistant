#!/usr/bin/env python3
"""Clean up codebase by identifying and removing dead code, unused imports, etc.

This script helps identify:
- Unused imports
- Dead code (functions/classes never called)
- Commented-out code blocks
- Duplicate code patterns
- Orphaned files
"""

import sys
import ast
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
import logging
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CodeAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze Python code."""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.imports: Set[str] = set()
        self.from_imports: Dict[str, Set[str]] = defaultdict(set)
        self.functions: Set[str] = set()
        self.classes: Set[str] = set()
        self.calls: Set[str] = set()
        self.attributes: Set[str] = set()
        self.commented_blocks: List[Tuple[int, int, str]] = []
        
    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
            if alias.asname:
                self.imports.add(alias.asname)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        if node.module:
            for alias in node.names:
                self.from_imports[node.module].add(alias.name)
                if alias.asname:
                    self.from_imports[node.module].add(alias.asname)
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node):
        self.functions.add(node.name)
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node):
        self.functions.add(node.name)
        self.generic_visit(node)
    
    def visit_ClassDef(self, node):
        self.classes.add(node.name)
        self.generic_visit(node)
    
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self.calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.attributes.add(node.func.attr)
        self.generic_visit(node)
    
    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name):
            self.attributes.add(node.attr)
        self.generic_visit(node)


def analyze_file(file_path: Path) -> Dict:
    """Analyze a Python file.
    
    Returns:
        Dict with analysis results
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for commented-out code blocks
        commented_blocks = find_commented_blocks(content)
        
        # Parse AST
        try:
            tree = ast.parse(content, filename=str(file_path))
            analyzer = CodeAnalyzer(file_path)
            analyzer.visit(tree)
            
            return {
                "imports": analyzer.imports,
                "from_imports": dict(analyzer.from_imports),
                "functions": analyzer.functions,
                "classes": analyzer.classes,
                "calls": analyzer.calls,
                "attributes": analyzer.attributes,
                "commented_blocks": commented_blocks,
                "error": None
            }
        except SyntaxError as e:
            return {
                "imports": set(),
                "from_imports": {},
                "functions": set(),
                "classes": set(),
                "calls": set(),
                "attributes": set(),
                "commented_blocks": commented_blocks,
                "error": f"Syntax error: {e}"
            }
    except Exception as e:
        return {
            "error": f"Error reading file: {e}"
        }


def find_commented_blocks(content: str) -> List[Tuple[int, int, str]]:
    """Find large commented-out code blocks.
    
    Returns:
        List of (start_line, end_line, preview) tuples
    """
    lines = content.split('\n')
    blocks = []
    in_block = False
    block_start = 0
    block_lines = []
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Check for commented lines (but not docstrings or single-line comments)
        if stripped.startswith('#') and len(stripped) > 2:
            if not in_block:
                in_block = True
                block_start = i
                block_lines = [stripped]
            else:
                block_lines.append(stripped)
        else:
            if in_block and len(block_lines) >= 3:  # At least 3 lines of comments
                blocks.append((
                    block_start,
                    i - 1,
                    '\n'.join(block_lines[:5])  # Preview first 5 lines
                ))
            in_block = False
            block_lines = []
    
    # Check final block
    if in_block and len(block_lines) >= 3:
        blocks.append((
            block_start,
            len(lines),
            '\n'.join(block_lines[:5])
        ))
    
    return blocks


def find_unused_imports(project_root: Path) -> Dict[str, List[str]]:
    """Find unused imports across the project.
    
    Returns:
        Dict mapping file paths to list of unused imports
    """
    python_files = list(project_root.rglob("*.py"))
    all_imports: Dict[str, Set[str]] = defaultdict(set)
    all_calls: Dict[str, Set[str]] = defaultdict(set)
    
    # Analyze all files
    for file_path in python_files:
        if 'venv' in str(file_path) or '__pycache__' in str(file_path):
            continue
        
        analysis = analyze_file(file_path)
        if analysis.get("error"):
            continue
        
        rel_path = str(file_path.relative_to(project_root))
        all_imports[rel_path] = analysis["imports"] | set().union(*analysis["from_imports"].values())
        all_calls[rel_path] = analysis["calls"] | analysis["attributes"]
    
    # Find unused imports
    unused = {}
    for file_path, imports in all_imports.items():
        calls = all_calls[file_path]
        unused_imports = [imp for imp in imports if imp not in calls and not any(imp.startswith(c) for c in calls)]
        if unused_imports:
            unused[file_path] = unused_imports
    
    return unused


def find_dead_code(project_root: Path) -> Dict[str, List[str]]:
    """Find functions and classes that are never called.
    
    Returns:
        Dict mapping file paths to list of unused functions/classes
    """
    python_files = list(project_root.rglob("*.py"))
    all_definitions: Dict[str, Set[str]] = defaultdict(set)
    all_calls: Dict[str, Set[str]] = defaultdict(set)
    
    # Analyze all files
    for file_path in python_files:
        if 'venv' in str(file_path) or '__pycache__' in str(file_path):
            continue
        
        analysis = analyze_file(file_path)
        if analysis.get("error"):
            continue
        
        rel_path = str(file_path.relative_to(project_root))
        all_definitions[rel_path] = analysis["functions"] | analysis["classes"]
        all_calls[rel_path] = analysis["calls"]
    
    # Find unused definitions
    # A definition is used if it's called anywhere in the project
    all_calls_flat = set().union(*all_calls.values())
    dead_code = {}
    
    for file_path, definitions in all_definitions.items():
        unused = [d for d in definitions if d not in all_calls_flat]
        # Exclude __init__ and main functions (they're entry points)
        unused = [d for d in unused if d not in ['__init__', 'main', '__main__']]
        if unused:
            dead_code[file_path] = unused
    
    return dead_code


def find_orphaned_files(project_root: Path) -> List[str]:
    """Find Python files that are never imported.
    
    Returns:
        List of orphaned file paths
    """
    python_files = list(project_root.rglob("*.py"))
    imported_modules: Set[str] = set()
    
    # Find all imports
    for file_path in python_files:
        if 'venv' in str(file_path) or '__pycache__' in str(file_path):
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            tree = ast.parse(content, filename=str(file_path))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_modules.add(node.module.split('.')[0])
        except Exception:
            continue
    
    # Find files that are never imported
    orphaned = []
    for file_path in python_files:
        if 'venv' in str(file_path) or '__pycache__' in str(file_path):
            continue
        if file_path.name == '__init__.py':
            continue
        
        # Get module name
        rel_path = file_path.relative_to(project_root)
        module_parts = rel_path.parts[:-1] + (rel_path.stem,)
        module_name = '.'.join(module_parts)
        
        # Check if it's imported
        if module_name not in imported_modules and not any(m.startswith(module_name) for m in imported_modules):
            # Check if it's a main/script file
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if '__main__' in content or 'if __name__' in content:
                    continue  # It's a script, not a module
            except Exception:
                pass
            
            orphaned.append(str(rel_path))
    
    return orphaned


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Analyze codebase for dead code, unused imports, etc."
    )
    parser.add_argument(
        '--project-root',
        type=str,
        default=None,
        help='Project root directory (default: current directory)'
    )
    parser.add_argument(
        '--unused-imports',
        action='store_true',
        help='Find unused imports'
    )
    parser.add_argument(
        '--dead-code',
        action='store_true',
        help='Find dead code (unused functions/classes)'
    )
    parser.add_argument(
        '--orphaned-files',
        action='store_true',
        help='Find orphaned files (never imported)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Run all checks'
    )
    
    args = parser.parse_args()
    
    # Determine project root
    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        script_dir = Path(__file__).parent.resolve()
        project_root = script_dir.parent
    
    logger.info(f"Project root: {project_root}")
    logger.info("")
    
    if args.all or args.unused_imports:
        logger.info("=" * 60)
        logger.info("Finding unused imports...")
        logger.info("=" * 60)
        unused_imports = find_unused_imports(project_root)
        if unused_imports:
            for file_path, imports in unused_imports.items():
                logger.info(f"\n{file_path}:")
                for imp in imports:
                    logger.info(f"  - {imp}")
        else:
            logger.info("No unused imports found.")
        logger.info("")
    
    if args.all or args.dead_code:
        logger.info("=" * 60)
        logger.info("Finding dead code...")
        logger.info("=" * 60)
        dead_code = find_dead_code(project_root)
        if dead_code:
            for file_path, definitions in dead_code.items():
                logger.info(f"\n{file_path}:")
                for defn in definitions:
                    logger.info(f"  - {defn}")
        else:
            logger.info("No dead code found.")
        logger.info("")
    
    if args.all or args.orphaned_files:
        logger.info("=" * 60)
        logger.info("Finding orphaned files...")
        logger.info("=" * 60)
        orphaned = find_orphaned_files(project_root)
        if orphaned:
            for file_path in orphaned:
                logger.info(f"  - {file_path}")
        else:
            logger.info("No orphaned files found.")
        logger.info("")
    
    if not (args.all or args.unused_imports or args.dead_code or args.orphaned_files):
        logger.info("No checks specified. Use --all or specific flags.")
        logger.info("Available flags: --unused-imports, --dead-code, --orphaned-files, --all")


if __name__ == '__main__':
    main()
