import sys

sys.path.insert(
    0,
    "app"
)


from services.assistant_dependency_validator_service import (
    AssistantDependencyValidatorService
)



def test_dependency_validator_detects_cycle():


    validator = (
        AssistantDependencyValidatorService()
    )


    actions = [

        {

            "title":
                "A",

            "depends_on":
                [
                    "C"
                ]

        },

        {

            "title":
                "B",

            "depends_on":
                [
                    "A"
                ]

        },

        {

            "title":
                "C",

            "depends_on":
                [
                    "B"
                ]

        }

    ]


    result = (
        validator.validate(
            actions
        )
    )


    assert (
        result["error"]
        ==
        True
    )