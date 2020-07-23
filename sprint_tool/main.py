from jira import JIRA
import jira
import argparse
from datetime import datetime, timedelta
import ast
import copy
import os
import sys
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def run():
    args = parse_args()
    print(args)
    options = {
        'server': args.jira_server,
        'agile_rest_path': 'agile',
        'verify': False
    }
    jira_agile_instance = JIRA(options,
                               auth=(args.jira_user,
                                     args.jira_password))

    if args.roll_sprints:

        current_sprints = get_current_sprints(jira_agile_instance,
                                              args.jira_board)

        if can_sprint_roll_over(current_sprints[-1]) or args.force:

            # Get lists of the current open sprints and the future sprints for this
            # board.
    
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
            
            print("Yay, the sprint rolled over!!")
        else:
            print("Won't roll over the sprint since it's not the time. You can force it by using --force.")

    elif args.report:
        report(jira_agile_instance, args.sprint_name, args.jira_board,
                args.template, args.output)
    elif args.copy_epic_to_task:
        if not args.project_id or not args.epic_id or not \
                (args.role or args.assignees):
            print("To copy an epic you must input project, epic and role")
            sys.exit()
        copy_epic_to_task(jira_agile_instance, args.project_id, args.epic_id,
                          args.role, args.watchers, args.assignees,
                          args.labels, args.prefixes)
    elif args.ticket_comment:
        comment_by_query(jira_agile_instance, args.ticket_comment_query,
                         args.ticket_comment, args.ticket_comment_manager_cc,
                         args.ticket_comment_manager_ldap,
                         args.ticket_comment_manager_ldapbasedn)


def create_new_sprint(jira_instance, board_id, sprint_name):
    print('Creating new sprint')
    print(sprint_name)
    jira_instance.create_sprint(sprint_name, board_id)


def get_unfinished_issue_keys(jira_instance, board_id, sprint_id):
    jql_query = "sprint={sprint_id} AND status != DONE".format(
        sprint_id=sprint_id)
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


def comment_by_query(jira_instance, query, comment, cc_to_manager,
                     ldap_server, basedn):
    """Adds a comment to tickets of the specified epic that are in the TODO
       state. and adds a CC to the users manager"""

    print("Add Comment to tickets in query results")

    for issue in jira_instance.search_issues(query, maxResults=400):
        assignee = issue.fields.assignee.key
        if cc_to_manager:
            # this is here because it is only required for this part of this
            # function. So it is not a requirement for the whole script
            import ldap
            l = ldap.initialize(ldap_server)
            l_filter = "uid=%s" % assignee
            l_attr = ["manager"]
            l_scope = ldap.SCOPE_SUBTREE
            ldap_result_id = l.search(basedn, l_scope, l_filter, l_attr)
            # only expecting a single result per query
            result_type, result_data = l.result(ldap_result_id, 0)
            if result_data:
                manager_dn = result_data[0][1]["manager"][0]
                manager = ldap.explode_dn(manager_dn)[0].split("=")[1]
                newcomment = "CC: [~%s]\n\n%s" % \
                    (manager, comment)
        else:
            newcomment = comment
        jira_instance.add_comment(issue.key, newcomment)


def copy_epic_to_task(jira_instance, project_id, epic_id, copy_to_role,
                      watchers, assignees, labels, prefixes):
    """copies an epic into tasks assigned to all the users in a specified role
       or to the specified list of assignees. Assignees has higher priority.
       If there are prefixes, unique is prefix + summary, which allows the
       same assignee multiple tickets. Else, it is one ticket per person"""

    print('Copy epic to tasks')
    print(epic_id)

    def get_values(field, f_name=None):
        """inner function that gets the current values out of jira objects"""
        f = f_name or "id"
        if isinstance(field, list):
            return [{f: getattr(val, f)} for val in field]
        else:
            return {f: getattr(field, f)}

    # if a role is passed in, get role users and put in assignee list.
    if not assignees:
        role_id = jira_instance.project_roles(project_id)[copy_to_role]["id"]
        actors = jira_instance.project_role(project_id, role_id).actors
        assignees = [actor.name for actor in actors]
    # verify that there is one user per prefix and that all expected assignees
    # have a prefix
    if prefixes:
        prefix_set = set([prefixes[prefix][0] for prefix in prefixes])
        if set(assignees) != prefix_set:
            print("prefixes are unique and can only have one assignee")
            print("These users are assignees with no prefixes: %s" % \
                (set(assignees).difference(prefix_set)))
            print("These users have prefixes but are not assignees: %s" % \
                (prefix_set.difference(set(assignees))))
            sys.exit()
        for prefix in prefixes:
            if len(prefixes[prefix]) != 1:
                print("If you use prefixes, they are unique per user")
                sys.exit()

    # find custom field names to get epic field
    custom_map = {fld['name']: fld['id'] for fld in jira_instance.fields()}
    epic = jira_instance.issue(epic_id)
    epic_flds = {"issuetype": {"name": "Task"},
                 custom_map["Epic Link"]: epic_id,
                 "project": get_values(epic.fields.project),
                 "summary": epic.fields.summary,
                 "description": epic.fields.description,
                 "labels": [],
                 "components": get_values(epic.fields.components),
                 "fixVersions": get_values(epic.fields.fixVersions),
                 "priority": get_values(epic.fields.priority),
                 "reporter": get_values(epic.fields.reporter, "name"),
                 "duedate": epic.fields.duedate}
    # gets the list of tasks already assigned to the epic to prevent dups
    # unique is either summary, if prefixes, or assignee
    # max results defaults to 50, we set 100 as we are currently well below.
    existing = [issue.fields.summary if prefixes
                else issue.fields.assignee.name for issue in
                jira_instance.search_issues(
                    'project=%s and issueType=Task and "Epic Link"=%s' %
                    (project_id, epic_id), maxResults=100)]
    task_fields = []
    for assignee in assignees:
        summary_prefix = [prefix for prefix in prefixes
                          if prefixes[prefix][0] == assignee]
        fields = copy.deepcopy(epic_flds.copy())
        fields["assignee"] = {"name": assignee}
        if labels:
            for label in labels:
                if assignee in labels[label]:
                    fields["labels"].append(label)
        if prefixes:
            summary = fields["summary"]
            for prefix in summary_prefix:
                fields = copy.deepcopy(fields.copy())
                fields["summary"] = "[%s] %s" % (prefix, summary)
                if fields["summary"] not in existing:
                    task_fields.append(fields)
        else:
            if assignee not in existing:
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
                    for watcher in watchers:
                        if result["input_fields"]["assignee"]["name"] \
                                in watchers[watcher]:
                            try:
                                jira_instance.add_watcher(
                                    result["issue"].key, watcher)
                            except jira.exceptions.JIRAError:
                                print ("error adding watcher: %s, %s" %
                                       (result["issue"].key, watcher))
            else:
                error += 1
                print("%s - %s" % (result["input_fields"]["assignee"]["name"],
                      result["error"]))
    print("Successful: %s\nErrors: %s\nExisting Tasks: %s\n" %
          (success, error, existing))


def find_current_sprint_id(sprints, sprint_name):
    sprint_id = None

    for sprint in sprints:
        # Split the sprint string into name and number then trim whitespace
        split = [token.strip() for token in sprint.name.split('#')]
        if sprint_name == split[0]:
            sprint_id = sprint.id

    print('Current sprint:')
    print(sprint_id)
    return sprint_id


# This should probably have different logic allowing for a different token to
# split on or just matching numbers at the end of the string,
# but this works for now.
def find_new_sprint_name(sprints, sprint_name):
    sprint_numbers = []
    for sprint in sprints:
        # Split the sprint string into name and number then trim whitespace
        split = [token.strip() for token in sprint.name.split('#')]
        if sprint_name == split[0]:
            sprint_numbers.append(split[1])
    sprint_numbers.sort()
    next_sprint_number = int(sprint_numbers[-1]) + 1
    return "{sprint_name} #{sprint_number}".format(
        sprint_name=sprint_name, sprint_number=next_sprint_number)


def find_next_sprint_id(sprints, sprint_name):
    sprint_id = None
    sprint_number = None

    for sprint in sprints:
        # Split the sprint string into name and number then trim whitespace
        split = [token.strip() for token in sprint.name.split('#')]
        print("SPLIT LAST")
        print(split)
        print(split[-1])
        split_sprint_number = int(split[-1])
        if sprint_name == split[0]:
            # Find the lowest sprint number in the list and its id
            if (sprint_number is None) or \
                    (split_sprint_number < sprint_number):
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


def move_issues_to_next_sprint(
        jira_agile_instance, next_sprint_id, issue_keys):
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


def flatten(d, parent_key='', sep='_'):
    """
    https://stackoverflow.com/a/6027615
    """
    import collections
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, collections.MutableMapping):
            items.extend(flatten(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            i = 0
            for sk in v:
                if isinstance(v, collections.MutableMapping):
                    items.extend(flatten(sk, new_key + sep + str(i) , sep=sep).items())
                else:
                    items.append((new_key + sep + str(i), sk))
                i += 1
        else:
            items.append((new_key, v))
    return dict(items)

def jira2dict(item):
    data = {}
    raw = item if isinstance(item, dict) else vars(item)
    good = (str, int, dict, list, bool)
    for (key,value) in raw.items():
        if '_' not in key and isinstance(value, good):
            data[key] = value
    return data

def report(jira_instance, sprint_name, board, template, output):
    report = []
    current_sprints = get_current_sprints(jira_instance, board)
    sprint_id = find_current_sprint_id(current_sprints, sprint_name)
    issues = jira_instance.search_issues("sprint={sprint_id}",
                                         expand="changelog")
    for issue in issues:
        issue_data = jira2dict(issue)
        fields = jira2dict(issue.raw['fields'])
        events = []
        for event in issue.changelog.histories:
            events.append({
                'event': jira2dict(event),
                'author': jira2dict(event.author),
                'changes': [jira2dict(item) for item in event.items]
                })
        worklogs = []
        for worklog in jira_instance.worklogs(issue):
            worklogs.append({
                'worklog': jira2dict(worklog),
                'author': jira2dict(worklog.author)})
        report.append({
            'issue': issue_data,
            'fields': fields,
            'events': events,
            'worklogs': worklogs
            })
    with open(output + '.json', 'w') as file_:
        import json
        json.dump(report, file_, indent=4, sort_keys=True, default=lambda o: '<not serializable>')
    from jinja2 import Environment, FileSystemLoader
    import arrow
    env = Environment(loader=FileSystemLoader('./'),
                      extensions=['jinja2.ext.loopcontrols'])
    def datetimeformat(value):
        return arrow.get(value).date()

    def env_override(value, key):
        return os.getenv(key, value)

    env.filters['iso8601_to_time'] = datetimeformat
    env.filters['env_override'] = env_override
    template = env.get_template(template)
    with open(output, 'w') as file_:
        file_.write(template.render(data=report))


def can_sprint_roll_over(active_sprint):
    """
    Sprints are typically two weeks intervals.
    Check to see if we can
    """
    current_date = datetime.now().isoformat().split('T')[0]
    print("Current Date: %s" % current_date)
    end_date = active_sprint.endDate.split('T')[0]
    print("Sprint End Date: %s" % end_date)

    if current_date >= end_date:
        return True

    return False

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
                             Use either this or --role, but not both""")
    parser.add_argument('-b', '--board',
                        action='store',
                        type=str,
                        dest='jira_board',
                        help='Jira board to work with')
    parser.add_argument('--copy_epic_to_task',
                        action='store_true',
                        dest='copy_epic_to_task',
                        help='Copy the specified epic to tasks for everyone'
                             ' in the specified role')
    parser.add_argument('-e', '--epic',
                        action='store',
                        type=str,
                        dest='epic_id',
                        help='epic to work with')
    parser.add_argument('-j', '--project',
                        action='store',
                        type=str,
                        dest='project_id',
                        help='Project to work with')
    parser.add_argument('-l', '--sprint-length',
                        action='store',
                        type=int,
                        dest='sprint_length',
                        help='Sprint duration in weeks')
    parser.add_argument('--labels',
                        type=lambda labeldict: ast.literal_eval(labeldict),
                        action='store',
                        dest='labels',
                        help="""
                             Add label to tickets of specific users. This is a
                             a dictionary, label: list of users to label:
                             {"label1": ["to_label_1","to_label_2"],...}""")
    parser.add_argument('-p', '--password',
                        action='store',
                        type=str,
                        dest='jira_password',
                        help='User password for Jira login')
    parser.add_argument('--summary-prefix',
                        type=lambda prefixdict: ast.literal_eval(prefixdict),
                        action='store',
                        dest='prefixes',
                        help="""
                             Add prefixes to tickets of specific
                             users. This is a dictionary, same format as
                             labels. It is added to the title within brackets
                             (e.g. [prefix]). Prefixes are unique, so there
                             can be only one assignee per prefix""")
    parser.add_argument('--role',
                        action='store',
                        type=str,
                        dest='role',
                        help="""The role to process the actions against.
                                Either use this or --assignees, not both""")
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
    parser.add_argument('--ticket-comment',
                        action='store',
                        type=str,
                        dest='ticket_comment',
                        help='Comment on ticket')
    parser.add_argument('--ticket-comment-manager-cc',
                        action='store_true',
                        dest='ticket_comment_manager_cc',
                        default=False,
                        help='Comment on ticket')
    parser.add_argument('--ticket-comment-manager-ldap',
                        action='store',
                        type=str,
                        dest='ticket_comment_manager_ldap',
                        help='LDAP server to find out who the manager is')
    parser.add_argument('--ticket-comment-manager-ldapbasedn',
                        action='store',
                        type=str,
                        dest='ticket_comment_manager_ldapbasedn',
                        help='LDAP basedn to find out who the manager is')
    parser.add_argument('--ticket-comment-query',
                        action='store',
                        type=str,
                        dest='ticket_comment_query',
                        help='Query to use when adding comment')
    parser.add_argument('-u', '--user',
                        action='store',
                        type=str,
                        dest='jira_user',
                        help='Username for Jira login')
    parser.add_argument('--watch',
                        type=lambda watchdict: ast.literal_eval(watchdict),
                        action='store',
                        dest='watchers',
                        help="""
                             Add watchers for specific users. This is a
                             a dictionary, watcher: list of watchees:
                             {"watcher": ["to_watch_1","to_watch_2"]}""")
    parser.add_argument('--report',
                        action='store_true',
                        dest='report',
                        help="""
                             Create report for specified sprint
                        """)
    parser.add_argument('--template',
                        action='store',
                        dest='template',
                        default='report.html.j2',
                        type=str,
                        help='Path to Jinja template to process for the report')
    parser.add_argument('--output',
                        action='store',
                        dest='output',
                        default='report.html',
                        type=str,
                        help='Report output path')
    parser.add_argument('--force',
                        action='store_true',
                        dest='force',
                        help="""To force an action. Typically used with --roll-sprint
                        to force sprint roll over if it's before the end sprint date.""")
    args = parser.parse_args()

    return args
