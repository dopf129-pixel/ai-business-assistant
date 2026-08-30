from inspect import signature


def call_with_legacy_arity(
    method,
    modern_args,
    legacy_args,
):

    try:
        method_signature = signature(
            method
        )
    except (
        TypeError,
        ValueError,
    ):
        return method(
            *modern_args
        )

    try:
        method_signature.bind(
            *modern_args
        )
    except TypeError:
        method_signature.bind(
            *legacy_args
        )

        return method(
            *legacy_args
        )

    return method(
        *modern_args
    )
