"""Tools: managing the project's configurable lists.

Categories, issue types, milestones/versions and custom fields all share one
tool because they share one shape: add / update / delete a named item.
"""

from ..app import mcp
from .. import api
from ..common import D


@mcp.tool()
def manage_project_setting(
    kind: str,
    action: str,
    source: str = D,
    item_id: int = 0,
    name: str = "",
    description: str = "",
    color: str = "",
    start_date: str = "",
    release_due_date: str = "",
    archived: bool = False,
    field_type_id: int = 0,
    required: bool = False,
    substitute_issue_type_id: int = 0,
) -> dict:
    """Create, rename or delete the project's configurable lists — categories,
    issue types, milestones/versions and custom fields.
    Read the current values with get_project_metadata first.
    ⚠️ Deletes are IRREVERSIBLE — confirm with user before calling.

    Args:
        kind: What to manage — 'category' (カテゴリー), 'issue_type' (種別),
              'milestone' (マイルストーン / 発生バージョン), or 'custom_field'.
        action: 'add', 'update' or 'delete'.
        source: Source name from get_sources. Empty = default source.
        item_id: Id of the item to update or delete (from get_project_metadata).
                 Ignored for action='add'.
        name: Name for add/update. Empty on update = keep current.
        description: Milestone or custom-field description.
        color: Issue-type colour hex. Allowed: #e30000 #990000 #934981 #814fbc
               #2779c4 #007e9a #7ea800 #ff9200 #ff3265 #666665. Default #e30000
               when adding an issue type.
        start_date: Milestone start date (YYYY-MM-DD).
        release_due_date: Milestone release due date (YYYY-MM-DD).
        archived: kind='milestone', action='update' — True archives the milestone.
        field_type_id: Custom field type when adding — 1=Text 2=TextArea 3=Numeric
                       4=Date 5=SingleList 6=MultipleList 7=CheckBox 8=Radio.
        required: Custom field — True makes it mandatory on issue creation.
        substitute_issue_type_id: Required when deleting an issue type — existing
                                  issues are migrated to this type.

    Returns:
        dict: the created / updated / deleted object as returned by Backlog,
        or {'error': message} for an unknown kind/action or a missing argument.
        The metadata cache is cleared on success so later name lookups see the change.
    """
    pkey = api.project_key(source)
    paths = {
        "category":     f"/projects/{pkey}/categories",
        "issue_type":   f"/projects/{pkey}/issueTypes",
        "milestone":    f"/projects/{pkey}/versions",
        "custom_field": f"/projects/{pkey}/customFields",
    }
    if kind not in paths:
        return {"error": f"Unknown kind '{kind}'. Valid: {list(paths)}"}
    base = paths[kind]

    if action == "delete":
        if not item_id:
            return {"error": "item_id is required for action='delete'"}
        params = None
        if kind == "issue_type":
            if not substitute_issue_type_id:
                return {"error": "substitute_issue_type_id is required to delete an issue type"}
            params = {"substituteIssueTypeId": substitute_issue_type_id}
        res = api.delete(source, f"{base}/{item_id}", params)
        api.clear_meta_cache()
        return res

    if action not in ("add", "update"):
        return {"error": f"Unknown action '{action}'. Use 'add', 'update' or 'delete'."}

    data: dict = {}
    if name:
        data["name"] = name
    if description:
        data["description"] = description

    if kind == "issue_type":
        if color:
            data["color"] = color
        elif action == "add":
            data["color"] = "#e30000"
    elif kind == "milestone":
        if start_date:
            data["startDate"] = start_date
        if release_due_date:
            data["releaseDueDate"] = release_due_date
        if archived and action == "update":
            data["archived"] = "true"
    elif kind == "custom_field":
        if action == "add":
            if not field_type_id:
                return {"error": "field_type_id is required to add a custom field"}
            data["typeId"] = field_type_id
        if required:
            data["required"] = "true"

    if action == "add":
        if not name:
            return {"error": "name is required for action='add'"}
        res = api.post(source, base, data)
    else:
        if not item_id:
            return {"error": "item_id is required for action='update'"}
        if not data:
            return {"error": "Nothing to update — pass at least one field"}
        res = api.patch(source, f"{base}/{item_id}", data)

    api.clear_meta_cache()
    return res
