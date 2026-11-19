"""Keep source discovery and dependency scanning in PlatformIO's normal pipeline."""
Import("env")
env.Replace(SRC_FILTER=["-<*>", "+<src/services/ble_service.cpp>", "+<src/services/brady.cpp>",
                        "+<fork/brady-test/main.cpp>", "+<fork/brady-test/adapters.cpp>"])
env.Replace(PROJECT_SRC_DIR=env.subst("$PROJECT_DIR"))
env.Append(CPPPATH=[env.subst("$PROJECT_DIR/src")])
