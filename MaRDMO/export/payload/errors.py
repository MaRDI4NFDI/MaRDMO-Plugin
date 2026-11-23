'''The errors of the export: the user's to fix, or the portal's.'''


class DocumentationProblem(ValueError):
    '''The documentation cannot be exported as it is; the user has to change it.

    Raised during the export, after the checks, for problems that show only
    in the payload or against the MaRDI Portal (e.g. an item that exists
    already, a symbol that stands for another quantity there).
    '''


class PortalUnavailable(ValueError):
    '''The MaRDI Portal did not answer a check the export needs; nothing was exported.'''
