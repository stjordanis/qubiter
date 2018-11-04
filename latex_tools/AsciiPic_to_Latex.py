import numpy as np
import copy as cp
from Controls import *


class AsciiPic_to_Latex:
    """
    This class can translate a Qubiter Picture file (which is a text file
    that contains an ASCII picture of a quantum circuit) into Latex code
    that can be compiled into a scholarly, publication quality eps or pdf
    picture of the circuit. The Latex code generated by this class calls
    commands from the package QCircuit, which in turn calls commands from
    the package xypic.

    References
    ----------
    1. Bryan Eastin, S. Flammia, "Q-circuit Tutorial",
    https://arxiv.org/abs/quant-ph/0406003v2
    2. K.H. Rose, "xypic users's guide"
    (There is also a much longer "xypic reference manual"

    You can use the Latex code produced by this class as a starting point.
    You can tweak the code by hand by adding annotations in Latex or by
    changing various parameters as explained in the xypic and Qcircuit
    documentation.

    Instead of going from Qubiter Picture file to Latex code directly,
    this class inserts an intermediate translation step that we call a
    Mosaic ascii picture. A Mosaic picture is a simplified, abridged version
    of a Qubiter "native" Picture file. In Qubiter native pictures,
    each gate is made up of multiple bonds, and each bond is 4 characters
    long. A Mosaic picture uses 1 character per bond instead of 4, usually
    retaining only the first character of each bond of the counterpart
    Qubiter native picture. Hence, a Mosaic picture is exactly 1/4 as long
    as its Qubiter native picture counterpart. Qubiter native pictures and
    Mosaic pictures can both be machine generated by Qubiter or written by
    hand. Because they are 1/4 as long, Mosaic pictures are easier to write
    by hand than Qubiter native pictures.

    Here is a quantum circuit with 7 qubits and 9 gates expressed in Qubiter
    native picture format and in Mosaic picture format. In both pictures,
    time points downwards. Each line (row) represents one gate, or one unit
    of time. Columns 0, 4, 8, ... represent a qubit in the Qubiter native pic.

    Qubiter native pic:

    |   X---+---+---@   |   |
    |   Y---+---O---@---O   |
    |   H   |   |   |   |   |
    |   <---+---+--->   |   |
    M   |   |   |   |   |   |
    @---X   |   |   |   |   |
    @---+---+---+---+---X   |
    @---+---+---O---+---X   |

    Mosaic pic:

    |X++@||
    |Y+O@O|
    |H|||||
    |<++>||
    M||||||
    @X|||||
    @++++X|
    @++O+X|

    As you can see, in the Mosaic pic, the white spaces and hyphens are
    omitted. The following symbols are kept:

    kept = [
        'H',  # Hadamard matrix
        'M',  # measurement of type 2
        'O',  # Control of type False
        '@',  # Control of type True
        'X',  # sigma_X Pauli matrix
        'Y',  # sigma_Y Pauli matrix
        'Z',  # sigma_Z Pauli matrix
        '<',  # left edge of swap gate
        '>',  # right edge of swap gate
        '|',  # wire connecting two times
        '+',  # '|' connecting 2 times crossed by a '-' connecting two qubits
        '$']  # place holder to be replaced in Latex by initial ket of a qubit

    In translating a Mosaic picture to Latex, this class will try to
    interpret each character of a Mosaic pic by using the "kept" list above.
    If you insert a character that it can't interpret, like for example an
    'A', it will translate that character to a Latex one qubit box with an
    'A' inside it. If a gate (=time=mosaic pic row) has at least one '?' in
    the mosaic pic, it will be drawn in the Latex with inter-qubit wiring.
    For example, a mosaic row |AA|?| will be drawn in the Latex with a box
    around each A and a box around the ? and a wire connecting all 3 boxes.

    In Qubiter native pics and Mosaic pics, time points down, the way we
    normally read  English. In the Latex pictures generated by this class,
    you can choose for time to point either from left to right (>) or vice
    versa (<). The > convention is more popular than the < convention,
    but the < convention is preferred by the cognoscenti because it
    recognizes that quantum circuit diagrams are merely a graphical
    representation of Dirac notation, and Dirac notation uses the <
    convention. Reversing a convention espoused by the universally popular
    Dirac notation is a totally needless complication.

    Attributes
    ----------
    gb_char_arr : np.ndarray
        This internal variable is a rectangular array of single characters,
        of shape (num_gates, num_bits), hence its name starts with gb. Each
        gate is a unit of time, and, as usual in Qubiter, the words bit and
        qubit are used interchangeably. To build this array, we start by
        splitting a Mosaic picture into a character array, then we make some
        modifications like adding a row of '$' characters and another of '|'
        characters as placeholders.
    gb_ch_is_measured : np.ndarray[bool]
        Internal variable, a bool array of the same shape as gb_char_arr.
        For each ch (aka character, node, vertex) entry in gb_char_arr,
        the corresponding bool entry of this array answers the question of
        whether or not that node is already measured (i.e., whether it
        occurs at the same qubit as an M node but after it).
    init_states : list[str]
        A list of num_bits many strings. Each string will be inserted inside
        a ket and displayed in the Latex picture as the starting state of a
        qubit. The strings in the list are ordered in top qubit to bottom
        qubit order.
    reverse_bits : bool
        Set to True iff you want qubit order in Mosaic pic to be reversed in
        Latex pic.
    reverse_gates : bool
        Set to True iff you want gate order in Mosaic pic to be reversed in
        Latex pic.
    time_dir : str
        time_dir = '<' if reverse_gates else '>'

    """
    def __init__(self, reverse_bits=True, reverse_gates=True):
        """
        Constructor

        Parameters
        ----------
        reverse_bits : bool
        reverse_gates : bool

        Returns
        -------
        None

        """

        self.reverse_bits = reverse_bits
        self.reverse_gates = reverse_gates
        self.time_dir = '<' if self.reverse_gates else '>'
        self.last_bit_on_top = self.reverse_bits

        # these change with each mosaic_word_list considered
        self.init_states = None
        self.gb_char_arr = None
        self.gb_ch_is_measured = None

    @staticmethod
    def qubiter_pic_file_to_mosaic_word_list(file_path, num_bits, ZL):
        """
        Reads Qubiter native pic file and returns a mosaic word list,
        which is a list of words all of which have the same number (
        =num_bits) of characters.

        Parameters
        ----------
        file_path : str
            Path to Qubiter native pic file.
        num_bits : int
            Number of qubits. The name of every native pic file generated by
            Qubiter states the value of num_bits.
        ZL : bool
            Set to True iff file is using Zero bit Last convention. Opposite
            of ZL is ZF (Zero First). The  name of every native pic file
            generated by Qubiter states either ZL or ZF.

        Returns
        -------
        list[str]

        """

        mosaic_word_list = []
        inside_if_m_block = False
        pic_file_in = open(file_path)
        while not pic_file_in.closed:
            line = pic_file_in.readline()
            if not line:
                pic_file_in.close()
                break
            line = line.replace('-', ' ')
            split_line = line.split()
            ch_list = []
            # print("..", split_line)
            if not inside_if_m_block:
                m_block_controls = Controls(num_bits)
            for vtx in split_line:
                # print('vtx', vtx)
                if vtx in ['@', '<', '>', '|', ':', '%', '+',
                           'H', 'M', 'O', 'Ph',
                           'Rx', 'Ry', 'Rz', 'R', 'X', 'Y', 'Z']:
                    ch_list.append(vtx[0])
                elif vtx in ['OP', '@P']:
                    ch_list.append('?')
                elif vtx in ['M1', 'M2']:
                    assert False, "unsupported measurement type"
                elif vtx in ['LOOP', 'NEXT']:
                    assert False, "loops not supported by Mosaic"
                elif vtx in ['NOTA', 'PRINT']:
                    break
                elif vtx == 'IF_M(':
                    inside_if_m_block = True
                    # m_block_controls should be empty at this point
                    assert not m_block_controls.bit_pos_to_kind
                    trols = split_line[1:-1]
                    # print('trols', trols)
                    trol_bits = [int(x[:-1]) for x in trols]
                    trol_kinds = \
                        [True if x[-1] == 'T' else False for x in trols]
                    for bit, kind in zip(trol_bits, trol_kinds):
                        m_block_controls.bit_pos_to_kind[bit] = kind
                    m_block_controls.refresh_lists()
                    break
                elif vtx == '}IF_M':
                    inside_if_m_block = False
                    break
                else:
                    assert False, "unexpected circuit node: '" + vtx + "'"
            # print("split_line", split_line)
            # ch_list may be empty in cases where broke out of vtx loop
            if ch_list:
                # give controls of if_m block to gates inside block
                assert len(ch_list) == num_bits, str(ch_list)
                if inside_if_m_block:
                    for bit, kind in m_block_controls.bit_pos_to_kind.items():
                        if not ZL:
                            ch_list[bit] = '@' if kind else 'O'
                        else:
                            ch_list[num_bits - bit - 1] = '@' if kind else 'O'
                # replace : by |
                ch_list = [ch if ch != ':' else '|' for ch in ch_list]

                # replace | by + when justified
                gate_has_inter_qubit_wires = False
                for ch in ch_list:
                    if ch in ['@', 'O', '<', '>', '+']:
                        gate_has_inter_qubit_wires = True
                        break
                if gate_has_inter_qubit_wires:
                    non_vertical_pos = [k for k in range(num_bits)
                                        if ch_list[k] != '|']
                    min_non_vert = min(non_vertical_pos)
                    max_non_vert = max(non_vertical_pos)
                    for k in range(min_non_vert+1, max_non_vert):
                        if ch_list[k] == '|':
                            ch_list[k] = '+'

                mosaic_word_list.append(''.join(ch_list))
        return mosaic_word_list

    def process_mosaic_word_list(self, mosaic_word_list, init_states):
        """
        Internal function that uses info in the input mosaic_word_list to
        fill certain attributes of the class.

        Parameters
        ----------
        mosaic_word_list : list[str]
        init_states : list[str]

        Returns
        -------
        None
               
        """

        word_list = cp.copy(mosaic_word_list)
        self.init_states = init_states

        num_bits = len(word_list[0])
        for word in word_list:
            assert len(word) == num_bits

        def repeated_ch(ch):
            return ''.join([ch]*num_bits)

        # extend end
        if not self.reverse_gates:
            # print(word_list, [repeated_ch('|')] )
            word_list = word_list + [repeated_ch('|')]
        else:
            word_list = [repeated_ch('|')] + word_list

        if init_states:
            word_list = [repeated_ch('$')] + word_list

        num_gates = len(word_list)
        char_list = []
        for word in word_list:
            char_list.extend(list(word))
        self.gb_char_arr = np.array(char_list).reshape((num_gates, num_bits))

        self.gb_ch_is_measured = np.zeros(
                    shape=(num_gates, num_bits), dtype=bool)
        for gate in range(num_gates):
            for bit in range(num_bits):
                if self.gb_char_arr[gate, bit] == 'M':
                    for gate1 in range(gate+1, num_gates):
                        self.gb_ch_is_measured[gate1, bit] = True

        # print('..', self.gb_ch_is_measured)
        for gate in range(num_gates):
            for bit in range(num_bits):
                if self.gb_ch_is_measured[gate, bit]:
                    assert self.gb_char_arr[gate, bit] in \
                        ['@', 'O', '|', '+'],\
                        "Only admissible ops on a measured qubit are @,O,|,+"

        # print("self.gb_char_arr=\n", self.gb_char_arr)

    @staticmethod
    def get_preface_latex():
        """
        Returns preface code of Latex document.

        Returns
        -------
        str
        """
        preface = "\\documentclass[12pt]{article}\n"
        preface += "\\usepackage{Qcircuit_v2, Qcircuit_extension}\n"
        preface += "\\begin{document}\n"
        preface += "\n\n"
        return preface

    @staticmethod
    def get_ending_latex():
        """
        Returns ending code of Latex document.

        Returns
        -------
        str
        """
        return "\\end{document}"

    def get_ckt_latex(self, mosaic_word_list, init_states=None):
        """
        Returns Latex code for quantum circuit described by the input
        mosaic_word_list.

        Parameters
        ----------
        mosaic_word_list : list[str]
        init_states : list[str]

        Returns
        -------
        str
        """

        self.process_mosaic_word_list(mosaic_word_list, init_states)

        latex_str = "\\begin{equation}\n\\begin{array}{c}\n"
        latex_str += "\\Qcircuit @C=2em @R=.4em {\n"

        num_bits = len(mosaic_word_list[0])
        num_gates = len(mosaic_word_list) + 2

        for bit in range(num_bits):
            _bit = bit
            if self.reverse_bits:
                _bit = num_bits - bit - 1
            if bit > 0:
                latex_str += '\\\\  % bit ' + str(bit) + '\n'
            else:
                latex_str += '% bit ' + str(bit) + '\n'
            for gate_num in range(num_gates):
                _gate_num = gate_num
                if self.reverse_gates:
                    _gate_num = num_gates - _gate_num - 1
                gate_char = self.gb_char_arr[_gate_num, _bit]
                is_m = self.gb_ch_is_measured[_gate_num, _bit]
                if gate_char == 'M':
                    if self.reverse_gates:
                        latex_str += '&\\Rmeter'
                    else:
                        latex_str += '&\\meter'
                elif gate_char == 'O':
                    latex_str += '&\\Cogate' if is_m else '&\\ogate'
                elif gate_char == 'X':
                    latex_str += '&\\timesgate'
                elif gate_char == '<':
                    if self.reverse_bits:
                        latex_str += '&\\darrowgate'
                    else:
                        latex_str += '&\\uarrowgate'
                elif gate_char == '>':
                    if self.reverse_bits:
                        latex_str += '&\\uarrowgate'
                    else:
                        latex_str += '&\\darrowgate'
                elif gate_char == '@':
                    latex_str += '&\\Cdotgate' if is_m else '&\\dotgate'
                elif gate_char == '|':
                    latex_str += '&\\cw' if is_m else '&\\qw'
                elif gate_char == '+':
                    latex_str += '&\\cw' if is_m else '&\\qw'
                elif gate_char == '$':
                    stick = '\\lstick' if not self.reverse_gates else ''
                    latex_str += '&' + stick + '{\\ket{' +\
                                 self.init_states[bit] + '}}'
                else:
                    latex_str += '&\gate{' + gate_char + '}'

                # add \qwx
                if self.reverse_bits:
                    bit_range = reversed(range(num_bits))
                else:
                    bit_range = range(num_bits)
                gate_ch_list = [self.gb_char_arr[_gate_num, k] for
                                k in bit_range]
                gate_has_inter_qubit_wires = False
                for ch in gate_ch_list:
                    # any gate-time with at least one '?' in mosaic pic
                    # will be drawn in latex with inter-qubit wiring
                    if ch in ['@', 'O', '<', '>', '+', '?']:
                        gate_has_inter_qubit_wires = True
                        break
                if gate_has_inter_qubit_wires:
                    non_vertical_pos = [k for k in range(num_bits)
                                        if gate_ch_list[k] != '|']
                    min_non_vert = min(non_vertical_pos)
                    max_non_vert = max(non_vertical_pos)
                    for k in range(min_non_vert, max_non_vert):
                        if bit-1 == k:
                            latex_str += '\qwx'

                latex_str += '\t\t% gate ' + str(gate_num) + '\n'
        latex_str += '}\n'
        latex_str += '\\end{array}\n\\end{equation}\n\n'

        return latex_str

if __name__ == "__main__":
    def main():

        def write_latex_file(file_out1):
            latex_str = AsciiPic_to_Latex.get_preface_latex()
            for rev_bits in [False, True]:
                last_bit_on_top = rev_bits
                for rev_gates in [False, True]:
                    # print('case', rev_bits, rev_gates)
                    time_dir = '<' if rev_gates else '>'
                    latex_str += "\nlast bit on top=" + str(last_bit_on_top)
                    latex_str += ", time dir= $" + time_dir + '$\n\n'
                    trans = AsciiPic_to_Latex(rev_bits, rev_gates)
                    latex_str += trans.get_ckt_latex(mosaic_word_list,
                                                     init_states)
            latex_str += AsciiPic_to_Latex.get_ending_latex()
            with open(file_out1, "w") as fi:
                fi.write(latex_str)

        # test 1 ---------------
        print('test 1')
        num_bits = 7
        file_out = "latex_test1.tex"
        mosaic_word_list = [
            "|X++@||",
            "|Y+O@O|",
            "HH|||||",
            "|<++>||",
            "M|M|M||",
            "@X|||||",
            "@++++X|",
            "@++O+X|",
            "|A|||B?"]
        init_states = [str(bit) for bit in range(num_bits)]
        # init_states = None

        print(mosaic_word_list)
        write_latex_file(file_out)

        # test 2 ---------------
        print("test 2")
        num_bits = 7
        file_in = "latex_test_pic.txt"
        mosaic_word_list = \
            AsciiPic_to_Latex.qubiter_pic_file_to_mosaic_word_list(
                file_in, num_bits, ZL=True)
        print(mosaic_word_list)

        # test 3 ---------------
        print('test 3')
        num_bits = 3
        file_in = '../io_folder/teleportation-with-ifs_3_ZLpic.txt'
        file_out = 'latex_test_telep.tex'
        mosaic_word_list = \
            AsciiPic_to_Latex.qubiter_pic_file_to_mosaic_word_list(
                file_in, num_bits, ZL=True)
        print(mosaic_word_list)
        init_states = ['0']*num_bits
        write_latex_file(file_out)
    main()


