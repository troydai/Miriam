def program():
    import argparse
    import sys
    import os.path

    import miriam.schedule_build
    import miriam.schedule_test
    import miriam.create_default_config
    from miriam._utility import config_logging

    default_user_config = os.path.expanduser('~/.miriam/config.yaml')

    parser = argparse.ArgumentParser(prog='Miriam')
    parser.add_argument('-v', dest='verbose', action='count', help='Verbose level. Can be accumulated.', default=0)
    parser.add_argument('-c', dest='config_file', type=argparse.FileType('r'),
                        default=open(default_user_config, 'r') if os.path.exists(default_user_config) else None,
                        help=f'Configuration file. Default: {default_user_config}')

    subparsers = parser.add_subparsers(help='Sub Commands')

    miriam.schedule_build.setup_arguments(subparsers.add_parser('build', help='Start a build job'))
    miriam.schedule_test.setup_arguments(subparsers.add_parser('test', help='Start a test job'))
    miriam.create_default_config.setup_arguments(subparsers)


    args = parser.parse_args()
    try:
        config_logging(args)
        args.func(args)
    except AttributeError:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    program()
