import sys

sys.path.insert(
    0,
    "app"
)


from services.assistant_dependency_validator_service import (
    AssistantDependencyValidatorService
)



def test_dependency_validator_detects_missing_dependency():


    validator = (
        AssistantDependencyValidatorService()
    )


    actions = [

        {

            "title":
                "Создать отчёт",

            "depends_on":
                [
                    "Несуществующее действие"
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