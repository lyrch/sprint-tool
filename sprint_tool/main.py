from jira import JIRA
import argparse
from datetime import datetime, timedelta
import re

def run():
    args = parse_args()
    print(args)

    options = { 'server': args.jira_server, 'agile_rest_path': 'agile' }
    jira_agile_instance = JIRA(options,
                               auth=(args.jira_user,
                               args.jira_password),
                              )

    greenhopper_options = { 'server': args.jira_server }
    jira_greenhopper_instance = JIRA(greenhopper_options,
                               auth=(args.jira_user,
                               args.jira_password),
                              )

    user = jira_agile_instance.current_user()

    # Get lists of the current open sprints and the future sprints for this
    # board.
    current_sprints = get_current_sprints(jira_agile_instance, args.jira_board)
    future_sprints = get_future_sprints(jira_agile_instance, args.jira_board)
    
    # Get the ids of the sprints we will want to close and start
    current_sprint_id = find_current_sprint_id(current_sprints, args.sprint_name)
    next_sprint_id = find_next_sprint_id(future_sprints, args.sprint_name)

    new_sprint_name = find_new_sprint_name(future_sprints, args.sprint_name)

    if args.roll_sprints:
        create_new_sprint(jira_agile_instance, args.jira_board, new_sprint_name)
        close_current_sprint(jira_agile_instance, args.jira_board, current_sprint_id)
        start_next_sprint(jira_agile_instance, args.jira_board, next_sprint_id)

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

def close_current_sprint(jira_instance, board_id, sprint_id):

    print('Close sprint')
    print(sprint_id)
    sprint = jira_instance.sprint(sprint_id)
    jira_instance.update_sprint(sprint_id,
                                name=sprint.name,
                                startDate=sprint.startDate,
                                endDate=sprint.endDate,
                                state='CLOSED')

def create_new_sprint(jira_instance, board_id, sprint_name):
    print('Creating new sprint')
    print(sprint_name)
    jira_instance.create_sprint(sprint_name, board_id)

def get_current_sprints(jira_instance, board_id):
    sprints = jira_instance.sprints(board_id, state='active')
    return sprints

def get_future_sprints(jira_instance, board_id):
    sprints = jira_instance.sprints(board_id, state='future')
    return sprints

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

def parse_args():
    parser = argparse.ArgumentParser(usage='sprint-tool [OPTIONS]')
    parser.add_argument('-b', '--board',
                        action='store',
                        type=str,
                        dest='jira_board',
                        help='Jira board to work with')
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
                            individual sprint would be 'Team Sprint #1' the text
                            prefix would be 'Team Sprint'
                            """)
    parser.add_argument('-u', '--user',
                        action='store',
                        type=str,
                        dest='jira_user',
                        help='Username for Jira login')
    args = parser.parse_args()

    return args

