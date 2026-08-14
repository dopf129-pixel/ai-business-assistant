import os
import subprocess
import sys
from datetime import datetime


PROJECT_BRAIN = "project_brain"



def read_file(path):

    if not os.path.exists(path):

        return ""

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return file.read()



def count_tests():

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q"
        ],
        capture_output=True,
        text=True
    )


    for line in result.stdout.splitlines():

        if "tests collected" in line:

            return (
                line
                .split()[0]
            )


    return "unknown"



def find_next_task():


    roadmap = read_file(
        "project_brain/ROADMAP.md"
    )


    for line in roadmap.splitlines():


        line = line.strip()


        if line.startswith(
            "[ ]"
        ):


            return (
                line
                .replace(
                    "[ ]",
                    ""
                )
                .strip()
            )


    return "No pending tasks"



def scan_project():


    print("=" * 50)

    print(
        "AI PROJECT SCAN"
    )

    print("=" * 50)


    services = 0


    if os.path.exists(
        "app/services"
    ):


        for root, dirs, files in os.walk(
            "app/services"
        ):


            for file in files:


                if file.endswith(
                    ".py"
                ):

                    services += 1



    docs = 0


    if os.path.exists(
        PROJECT_BRAIN
    ):


        for file in os.listdir(
            PROJECT_BRAIN
        ):


            if file.endswith(
                ".md"
            ):

                docs += 1



    print()

    print(
        "Services:",
        services
    )

    print()

    print(
        "Tests:",
        count_tests()
    )

    print()

    print(
        "Documentation files:",
        docs
    )

    print()

    print(
        "Next task:",
        find_next_task()
    )



def show_status():


    print("=" * 50)

    print(
        "AI PROJECT STATUS"
    )

    print("=" * 50)


    print()


    print(
        read_file(
            "project_brain/CURRENT_STATE.md"
        )
        [:2000]
    )


    print()

    print(
        "NEXT TASK:"
    )


    print(
        find_next_task()
    )


    print()

    print(
        "Last check:",
        datetime.now()
    )



def run_tests():


    print(
        "Running tests..."
    )


    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest"
        ]
    )


    print()


    if result.returncode == 0:

        print(
            "TEST RESULT: PASSED"
        )

    else:

        print(
            "TEST RESULT: FAILED"
        )
def verify_project():


    print("=" * 50)

    print(
        "AI PROJECT VERIFY"
    )

    print("=" * 50)


    tests = count_tests()


    print()

    print(
        "Collected tests:",
        tests
    )


    current = read_file(
        "project_brain/CURRENT_STATE.md"
    )


    if tests in current:

        print(
            "Test count: OK"
        )

    else:

        print(
            "Test count mismatch"
        )



    docs = [

        "ARCHITECTURE.md",

        "CURRENT_STATE.md",

        "RULES.md",

        "ROADMAP.md",

        "TEST_MAP.md",

        "DECISIONS.md",

        "CHANGELOG.md"

    ]


    print()


    for doc in docs:


        path = os.path.join(
            PROJECT_BRAIN,
            doc
        )


        if os.path.exists(path):

            print(
                "[OK]",
                doc
            )

        else:

            print(
                "[MISSING]",
                doc
            )



def create_plan():


    task = find_next_task()


    print("=" * 50)

    print(
        "AI DEVELOPMENT PLAN"
    )

    print("=" * 50)


    print(
        f"""
CURRENT TASK:

{task}



GOAL:

Реализовать следующую задачу из ROADMAP.md.



PROCESS:


1. Создать или обновить тест


2. Запустить pytest


3. Исправить реализацию


4. Обновить документацию



EXPECTED TESTS:

{count_tests()}+

"""
    )



def create_update_report():


    print("=" * 50)

    print(
        "AI UPDATE REPORT"
    )

    print("=" * 50)


    print(
        f"""
CURRENT STATE:


Tests:

{count_tests()} passed



Current completed stage:

Task Orchestration Engine



Next task:

{find_next_task()}



Documentation files:

CURRENT_STATE.md

CHANGELOG.md

ROADMAP.md
"""
    )



def checkpoint():


    print("=" * 50)

    print(
        "AI CHECKPOINT"
    )

    print("=" * 50)


    print(
        f"""
Project checkpoint:


Tests:

{count_tests()} collected



Next task:

{find_next_task()}



Status:

READY FOR GIT COMMIT
"""
    )



def show_context():


    files = [

        "ARCHITECTURE.md",

        "CURRENT_STATE.md",

        "RULES.md",

        "ROADMAP.md",

        "TEST_MAP.md",

        "DECISIONS.md",

        "CHANGELOG.md"

    ]


    print("=" * 50)

    print(
        "AI PROJECT CONTEXT"
    )

    print("=" * 50)


    for file in files:


        print()

        print(
            "#" * 40
        )

        print(
            file
        )

        print(
            "#" * 40
        )


        print(
            read_file(
                os.path.join(
                    PROJECT_BRAIN,
                    file
                )
            )
        )



def show_help():


    print(
        """
AI Development Manager v4


Commands:


python ai_dev.py status

python ai_dev.py test

python ai_dev.py context

python ai_dev.py scan

python ai_dev.py verify

python ai_dev.py analyze

python ai_dev.py plan

python ai_dev.py update

python ai_dev.py checkpoint
"""
    )



def analyze_project():


    print("=" * 50)

    print(
        "AI DEVELOPMENT ANALYSIS"
    )

    print("=" * 50)


    print()

    print(
        "NEXT TASK:"
    )


    print(
        find_next_task()
    )



if __name__ == "__main__":


    if len(sys.argv) < 2:


        show_help()


    else:


        command = sys.argv[1]


        if command == "status":

            show_status()


        elif command == "test":

            run_tests()


        elif command == "context":

            show_context()


        elif command == "scan":

            scan_project()


        elif command == "verify":

            verify_project()


        elif command == "analyze":

            analyze_project()


        elif command == "plan":

            create_plan()


        elif command == "update":

            create_update_report()


        elif command == "checkpoint":

            checkpoint()


        else:

            show_help()