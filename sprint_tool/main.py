from jira import JIRA
import jira
import argparse
from datetime import datetime, timedelta
import re
import ast

def run():
    args = parse_args()
    print(args)

    options = { 'server': args.jira_server, 'agile_rest_path': 'agile' }
    jira_agile_instance = JIRA(options,
                               auth=(args.jira_user,
                                     args.jira_password))

    user = jira_agile_instance.current_user()

    if args.roll_sprints:
        # Get lists of the current open sprints and the future sprints for this
        # board.
        current_sprints = get_current_sprints(jira_agile_instance,
                                              args.jira_board)
        future_sprints = get_future_sprints(jira_agile_instance,
                                            args.jira_board)

        # Get the ids of the sprints we will want to close and start
        current_sprint_id = find_current_sprint_id(current_sprints,
                                                   args.sprint_name)
        next_sprint_id = find_next_sprint_id(future_sprints,
                                             args.sprint_name)

        new_sprint_name = find_new_sprint_name(future_sprints,
                                               args.sprint_name)

        issue_keys = get_unfinished_issue_keys(jira_agile_instance,
                                               args.jira_board,
                                               current_sprint_id)
        create_new_sprint(jira_agile_instance,
                          args.jira_board,
                          new_sprint_name)
        close_current_sprint(jira_agile_instance,
                             args.jira_board,
                             current_sprint_id)
        start_next_sprint(jira_agile_instance,
                          args.jira_board,
                          next_sprint_id)
        move_issues_to_next_sprint(jira_agile_instance,
                                   next_sprint_id,
                                   issue_keys)
    elif args.copy_epic_to_task:
        if not args.project_id or not args.epic_id or not (args.role or args.assignees):
            print("To copy an epic you must input project, epic and role")
        copy_epic_to_task(jira_agile_instance, args.project_id, args.epic_id,
                          args.role, args.watchers, args.assignees)


def create_new_sprint(jira_instance, board_id, sprint_name):
    print('Creating new sprint')
    print(sprint_name)
    jira_instance.create_sprint(sprint_name, board_id)


def get_unfinished_issue_keys(jira_instance, board_id, sprint_id):
    jql_query = "sprint={sprint_id} AND status != DONE".format(sprint_id=sprint_id)
    unfinished_issues = jira_instance.search_issues(jql_query)
    issue_keys = []
    for issue in unfinished_issues:
        issue_keys.append(issue.key)
    return issue_keys

def close_current_sprint(jira_instance, board_id, sprint_id):

    print('Close sprint')
    print(sprint_id)
    sprint = jira_instance.sprint(sprint_id)
    jira_instance.update_sprint(sprint_id,
                                name=sprint.name,
                                startDate=sprint.startDate,
                                endDate=sprint.endDate,
                                state='CLOSED')

def copy_epic_to_task(jira_instance, project_id, epic_id, copy_to_role,
                      watchers, assignees):
    """copies an epic into tasks assigned to all the users in a specified role
       or to the specified list of assignees. Assignees has higher priority"""

    print('Copy epic to tasks')
    print(epic_id)

    def get_values(field, f_name=None):
        """inner function that gets the current values out of jira objects"""
        f = f_name or "id"
        if isinstance(field, list):
            return [{f: getattr(val, f)} for val in field]
        else:
            return {f: getattr(field, f)}

    # find custom field names to get epic field
    custom_map = {fld['name']: fld['id'] for fld in jira_instance.fields()}
    epic = jira_instance.issue(epic_id)
    epic_flds = {"issuetype": {"name": "Task"},
                 custom_map["Epic Link"]: epic_id,
                 "project": get_values(epic.fields.project),
                 "summary": epic.fields.summary,
                 "description": epic.fields.description,
                 "labels": epic.fields.labels,
                 "components": get_values(epic.fields.components),
                 "fixVersions": get_values(epic.fields.fixVersions),
                 "priority": get_values(epic.fields.priority),
                 "reporter": get_values(epic.fields.reporter, "name")}
    # gets the list of tasks already assigned to the epic to prevent dups
    existing = [issue.fields.assignee.name for issue in
                jira_instance.search_issues(
                    'project=%s and issueType=Task and "Epic Link"=%s' %
                    (project_id, epic_id))]
    task_fields = []
    if not assignees:
        role_id = jira_instance.project_roles(project_id)[copy_to_role]["id"]
        actors = jira_instance.project_role(project_id, role_id).actors
        for actor in actors:
            if actor.name not in existing:
                fields = epic_flds.copy()
                fields["assignee"] = get_values(actor, "name")
                task_fields.append(fields)
    else:
        for assignee in assignees:
            if assignee not in existing:
                fields = epic_flds.copy()
                fields["assignee"] = {"name": assignee}
                task_fields.append(fields)
    success = 0
    error = 0
    existing = len(existing)
    if task_fields:
        results = jira_instance.create_issues(task_fields)
        for result in results:
            if result["status"] == "Success":
                success += 1
                if watchers:
                    for watchman in watchers:
                        if result["input_fields"]["assignee"]["name"] \
                                in watchers[watchman]:
                            try:
                                jira_instance.add_watcher(
                                    result["issue"].key, watchman)
                            except jira.exceptions.JIRAError:
                                print ("error adding watcher: %s, %s" %
                                       (result["issue"].key, watchman))
            else:
                error += 1
                print("%s - %s" % (result["input_fields"]["assignee"]["name"],
                      result["error"]))
    print("Successful: %s\nErrors: %s\nExisting Tasks: %s\n" %
          (success, error, existing))


def find_current_sprint_id(sprints, sprint_name):
    sprint_id = None

    for sprint in sprints:
        # Split the sprint string into  the name and number then trim whitespace
        split = [token.strip() for token in sprint.name.split('#')]
        if sprint_name == split[0]:
            sprint_id = sprint.id

    print('Current sprint:')
    print(sprint_id)
    return sprint_id

# This should probably have different logic allowing for a different token to
# split on or just matching numbers at the end of the string, but this works for
# now.

def find_new_sprint_name(sprints, sprint_name):
    sprint_numbers = []
    for sprint in sprints:
        # Split the sprint string into  the name and number then trim whitespace
        split = [token.strip() for token in sprint.name.split('#')]
        if sprint_name == split[0]:
            sprint_numbers.append(split[1])
    sprint_numbers.sort()
    next_sprint_number = int(sprint_numbers[-1]) + 1
    return "{sprint_name} #{sprint_number}".format(sprint_name=sprint_name,
                                                   sprint_number=next_sprint_number)

def find_next_sprint_id(sprints, sprint_name):
    sprint_id = None
    sprint_number = None

    for sprint in sprints:
        # Split the sprint string into  the name and number then trim whitespace
        split = [token.strip() for token in sprint.name.split('#')]
        print("SPLIT LAST")
        print(split)
        print(split[-1])
        split_sprint_number = int(split[-1])
        if sprint_name == split[0]:
            # Find the lowest sprint number in the list and its id
            if (None == sprint_number) or (split_sprint_number < sprint_number):
                sprint_number = split_sprint_number
                sprint_id = sprint.id

    print('Next sprint:')
    print(sprint_id)
    return sprint_id

def get_current_sprints(jira_instance, board_id):
    sprints = jira_instance.sprints(board_id, state='active')
    return sprints

def get_future_sprints(jira_instance, board_id):
    sprints = jira_instance.sprints(board_id, state='future')
    return sprints

def move_issues_to_next_sprint(jira_agile_instance, next_sprint_id, issue_keys):
    jira_agile_instance.add_issues_to_sprint(next_sprint_id,
                                             issue_keys)

def start_next_sprint(jira_instance, board_id, sprint_id):
    start_date = datetime.now().isoformat()
    end_date = (datetime.now() + timedelta(days=14)).isoformat()

    print('Next Sprint')
    print(sprint_id)
    print('Start date')
    print(start_date)
    print('End date')
    print(end_date)
    sprint = jira_instance.sprint(sprint_id)
    jira_instance.update_sprint(sprint_id,
                                name=sprint.name,
                                startDate=start_date,
                                endDate=end_date,
                                state='ACTIVE')


def parse_args():
    parser = argparse.ArgumentParser(usage='sprint-tool [OPTIONS]')
    parser.add_argument('--assignees',
                        type=lambda assign:
                            ast.literal_eval(
                                "['%s']" % assign.replace(" ", "").
                                replace(",", "','")),
                        action='store',
                        dest='assignees',
                        help="""
                             Add users to assign tickets to in comma
                             seperated list.
                             Use either this or --role, but not both"""),
    parser.add_argument('-b', '--board',
                        action='store',
                        type=str,
                        dest='jira_board',
                        help='Jira board to work with'),
    parser.add_argument('--copy_epic_to_task',
                        action='store_true',
                        dest='copy_epic_to_task',
                        help='Copy the specified epic to tasks for everyone'
                             ' in the specified role'),
    parser.add_argument('-e', '--epic',
                        action='store',
                        type=str,
                        dest='epic_id',
                        help='epic to work with'),
    parser.add_argument('-j', '--project',
                        action='store',
                        type=str,
                        dest='project_id',
                        help='Project to work with'),
    parser.add_argument('-l', '--sprint-length',
                        action='store',
                        type=int,
                        dest='sprint_length',
                        help='Sprint duration in weeks')
    parser.add_argument('-p', '--password',
                        action='store',
                        type=str,
                        dest='jira_password',
                        help='User password for Jira login')
    parser.add_argument('--role',
                        action='store',
                        type=str,
                        dest='role',
                        help="""The role to process the actions against.
                                Either use this or --assignees, not both"""),
    parser.add_argument('-r', '--roll-sprints',
                        action='store_true',
                        dest='roll_sprints',
                        help='Actually change the sprints')
    parser.add_argument('-s', '--server',
                        action='store',
                        type=str,
                        dest='jira_server',
                        help='Jira server base url')
    parser.add_argument('-n', '--sprint-name',
                        action='store',
                        type=str,
                        dest='sprint_name',
                        help="""
                            Text prefix of the Sprint name, eg if an
                            individual sprint would be 'Team Sprint #1' the
                            text prefix would be 'Team Sprint'
                            """)
    parser.add_argument('-u', '--user',
                        action='store',
                        type=str,
                        dest='jira_user',
                        help='Username for Jira login'),
    parser.add_argument('--watch',
                        type=lambda watchdict: ast.literal_eval(watchdict),
                        action='store',
                        dest='watchers',
                        help="""
                             Add watchers for specific users. This is a
                             a dictionary, watcher: list of watchees:
                             {"watcher": ["to_watch_1","to_watch_2"]}""")
    args = parser.parse_args()

    return args
