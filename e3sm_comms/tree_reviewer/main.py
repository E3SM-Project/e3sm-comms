from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Configuration constants
INPUT_TREE_A = "/home/ac.forsyth2/ez/e3sm-comms-io/input/tree_reviewer/hierarchical_outline_20251203.txt"
INPUT_TREE_B = "/home/ac.forsyth2/ez/e3sm-comms-io/input/tree_reviewer/hierarchical_outline_20260109.txt"
OUTPUT_STEP_LIST = (
    "/home/ac.forsyth2/ez/e3sm-comms-io/output/tree_reviewer/tree_diff_output.txt"
)


@dataclass
class TreeNode:
    """Represents a node in the tree structure."""

    name: str
    children: List["TreeNode"] = field(default_factory=list)
    parent: Optional["TreeNode"] = None


def parse_tree(text: str) -> TreeNode:
    """Parse indented text into a tree structure."""
    lines = text.strip().split("\n")
    root = TreeNode(name="__root__")
    stack: List[Tuple[TreeNode, int]] = [(root, -2)]  # (node, indent_level)

    for line in lines:
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        name = line.strip()

        node = TreeNode(name=name)

        # Pop stack until we find the parent
        while stack and stack[-1][1] >= indent:
            stack.pop()

        parent = stack[-1][0]
        parent.children.append(node)
        node.parent = parent

        stack.append((node, indent))

    return root


def find_node(
    root: TreeNode, name: str, path_prefix: Optional[str] = None
) -> List[Tuple[TreeNode, str]]:
    """Find a node by name, optionally within a path prefix."""
    results: List[Tuple[TreeNode, str]] = []

    def search(node: TreeNode, current_path: str) -> None:
        if node.name == name:
            if path_prefix is None or current_path.startswith(path_prefix):
                results.append((node, current_path))
        for child in node.children:
            search(child, current_path + "/" + child.name)

    search(root, "")
    return results


def get_path(node: TreeNode) -> str:
    """Get the path from root to node."""
    path: List[str] = []
    current: Optional[TreeNode] = node
    while current and current.name != "__root__":
        path.append(current.name)
        current = current.parent
    return "/".join(reversed(path))


def tree_to_dict(root: TreeNode) -> Dict[str, Dict[str, Any]]:
    """Convert tree to dict with paths as keys."""
    result: Dict[str, Dict[str, Any]] = {}

    def traverse(node: TreeNode) -> None:
        if node.name != "__root__":
            path = get_path(node)
            parent_path = (
                get_path(node.parent)
                if node.parent and node.parent.name != "__root__"
                else None
            )
            result[path] = {
                "parent": parent_path,
                "children": [child.name for child in node.children],
            }
        for child in node.children:
            traverse(child)

    traverse(root)
    return result


# C901 'generate_diff' is too complex (37)
def generate_diff(tree_a_text: str, tree_b_text: str) -> List[str]:  # noqa: C901
    """Generate human-readable steps to convert tree A to tree B."""
    tree_a = parse_tree(tree_a_text)
    tree_b = parse_tree(tree_b_text)

    dict_a = tree_to_dict(tree_a)
    dict_b = tree_to_dict(tree_b)

    # Get node names (last component of path)
    def get_node_name(path: str) -> str:
        return path.split("/")[-1]

    # Build a mapping of node names to their paths
    name_to_paths_a: Dict[str, List[str]] = {}
    name_to_paths_b: Dict[str, List[str]] = {}

    for path in dict_a.keys():
        name = get_node_name(path)
        name_to_paths_a.setdefault(name, []).append(path)

    for path in dict_b.keys():
        name = get_node_name(path)
        name_to_paths_b.setdefault(name, []).append(path)

    # Find nodes by name
    names_a = set(name_to_paths_a.keys())
    names_b = set(name_to_paths_b.keys())

    added_names = names_b - names_a
    removed_names = names_a - names_b
    common_names = names_a & names_b

    # Track operations with their dependencies
    operations: List[Tuple[str, str, Optional[str]]] = (
        []
    )  # (type, description, depends_on_node)

    # Track removals (only report if not a descendant of another removed node)
    removed_paths = set()
    for name in removed_names:
        for path in name_to_paths_a[name]:
            removed_paths.add(path)

    # Filter out descendant removals
    independent_removals = set()
    for path in removed_paths:
        is_descendant = False
        for other_path in removed_paths:
            if path != other_path and path.startswith(other_path + "/"):
                is_descendant = True
                break
        if not is_descendant:
            independent_removals.add(path)

    for path in independent_removals:
        node_name = get_node_name(path)
        operations.append(
            ("delete", f"Delete '{node_name}' node (was at {path})", None)
        )

    # Track moves (only report if the node itself moved, not its ancestor)
    moved_paths = set()
    for name in common_names:
        paths_a = name_to_paths_a[name]
        paths_b = name_to_paths_b[name]

        for path_a in paths_a:
            parent_a = dict_a[path_a]["parent"]

            for path_b in paths_b:
                parent_b = dict_b[path_b]["parent"]

                if parent_a != parent_b:
                    moved_paths.add((path_a, path_b, name))
                    break

    # Filter out moves that are due to ancestor moves
    independent_moves = set()
    for path_a, path_b, name in moved_paths:
        is_descendant_move = False

        for other_path_a, other_path_b, other_name in moved_paths:
            if path_a != other_path_a and path_a.startswith(other_path_a + "/"):
                is_descendant_move = True
                break

        if not is_descendant_move:
            independent_moves.add((path_a, path_b, name))

    for path_a, path_b, name in independent_moves:
        parent_b = dict_b[path_b]["parent"]
        if parent_b:
            parent_name = get_node_name(parent_b)
            description = f"Move '{name}' node to be a child of '{parent_name}' node"
            # Move depends on parent existing
            operations.append(("move", description, parent_name))
        else:
            description = f"Move '{name}' node to root level"
            operations.append(("move", description, None))

    # Track additions (only report if not a descendant of another added node)
    added_paths = set()
    for name in added_names:
        for path in name_to_paths_b[name]:
            added_paths.add(path)

    # Filter out descendant additions
    independent_additions = set()
    for path in added_paths:
        is_descendant = False
        for other_path in added_paths:
            if path != other_path and path.startswith(other_path + "/"):
                is_descendant = True
                break
        if not is_descendant:
            independent_additions.add(path)

    for path in independent_additions:
        node_name = get_node_name(path)
        parent = dict_b[path]["parent"]
        if parent:
            parent_name = get_node_name(parent)
            description = f"Add '{node_name}' node as a child of '{parent_name}' node"
            # Addition depends on parent existing
            operations.append(("add", description, parent_name))
        else:
            description = f"Add '{node_name}' node at root level"
            operations.append(("add", description, None))

    # Sort operations logically:
    # 1. Deletions first (can always be done)
    # 2. Additions/Moves sorted by dependency (parents before children)
    sorted_steps: List[str] = []

    # Add all deletions first
    for op_type, description, _ in operations:
        if op_type == "delete":
            sorted_steps.append(description)

    # Process additions and moves with topological sort
    remaining_ops = [
        (op_type, description, depends_on)
        for op_type, description, depends_on in operations
        if op_type != "delete"
    ]

    # Track which nodes are now available (exist in tree A or have been added)
    available_nodes = names_a.copy()

    while remaining_ops:
        added_this_round = False

        for i, (op_type, description, depends_on) in enumerate(remaining_ops):
            # Can perform this operation if dependency is met
            if depends_on is None or depends_on in available_nodes:
                sorted_steps.append(description)

                # Extract the node name being added/moved
                if op_type == "add":
                    # Extract node name from "Add 'NodeName' node..."
                    node_name = description.split("'")[1]
                    available_nodes.add(node_name)

                remaining_ops.pop(i)
                added_this_round = True
                break

        # If we couldn't add anything, there might be a circular dependency
        # or all remaining operations can be done in any order
        if not added_this_round:
            for _, description, _ in remaining_ops:
                sorted_steps.append(description)
            break

    return sorted_steps


def main() -> None:
    """Main function to read files, generate diff, and write output."""
    try:
        with open(INPUT_TREE_A, "r") as f:
            tree_a = f.read()

        with open(INPUT_TREE_B, "r") as f:
            tree_b = f.read()

        steps = generate_diff(tree_a, tree_b)

        with open(OUTPUT_STEP_LIST, "w") as f:
            f.write(f"Steps to convert {INPUT_TREE_A} to {INPUT_TREE_B}:\n\n")
            if steps:
                for i, step in enumerate(steps, 1):
                    f.write(f"{i}. {step}\n")
            else:
                f.write("No changes needed - trees are identical!\n")

        print(f"Diff output written to {OUTPUT_STEP_LIST}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print(
            f"Make sure {INPUT_TREE_A} and {INPUT_TREE_B} exist in the current directory."
        )
    except Exception as e:
        print(f"Error processing files: {e}")


if __name__ == "__main__":
    main()
