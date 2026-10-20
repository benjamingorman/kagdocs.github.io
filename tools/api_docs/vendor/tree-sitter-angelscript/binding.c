/* Python adapter for the pinned grammar with build-stage KAG patches. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

typedef struct TSLanguage TSLanguage;
extern const TSLanguage *tree_sitter_angelscript(void);

static PyObject *language(PyObject *self, PyObject *args) {
    return PyCapsule_New((void *)tree_sitter_angelscript(), "tree_sitter.Language", NULL);
}

static PyMethodDef methods[] = {
    {"language", language, METH_NOARGS, "Return the AngelScript Tree-sitter language."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "kag_angelscript", NULL, -1, methods,
};

PyMODINIT_FUNC PyInit_kag_angelscript(void) {
    return PyModule_Create(&module);
}
