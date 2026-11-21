from evfl.common import StringHolder
from evfl.dic import DicReader, DicWriter
from evfl.enums import ContainerDataType
import evfl.event
from evfl.util import *

VariableDefPyTypes = typing.Union[int, bool, float, typing.List[int], typing.List[float]]

_SCALAR_VARIABLE_TYPES = (ContainerDataType.kInt, ContainerDataType.kBool, ContainerDataType.kFloat)
_ARRAY_VARIABLE_TYPES = (ContainerDataType.kIntArray, ContainerDataType.kFloatArray)

class VariableDef:
    """Initial value of a flowchart context variable."""
    __slots__ = ['type', 'value']
    def __init__(self, type: ContainerDataType, value: VariableDefPyTypes) -> None:
        self.type = type
        self.value = self._check_value(type, value)

    @staticmethod
    def _check_value(type: ContainerDataType, value: VariableDefPyTypes) -> VariableDefPyTypes:
        def is_int(v) -> bool:
            return isinstance(v, int) and not isinstance(v, bool)

        def is_number(v) -> bool:
            return is_int(v) or isinstance(v, float)

        if type == ContainerDataType.kInt and is_int(value):
            return value
        if type == ContainerDataType.kBool and isinstance(value, bool):
            return value
        if type == ContainerDataType.kFloat and is_number(value):
            return float(value) # type: ignore
        if type == ContainerDataType.kIntArray and isinstance(value, list) and all(is_int(v) for v in value):
            return value
        if type == ContainerDataType.kFloatArray and isinstance(value, list) and all(is_number(v) for v in value):
            return [float(v) for v in value]
        if type not in _SCALAR_VARIABLE_TYPES and type not in _ARRAY_VARIABLE_TYPES:
            raise ValueError(f'Unsupported variable type: {type!r}')
        raise ValueError(f'Invalid value for a {type.name} variable: {value!r}')

    def __repr__(self) -> str:
        return f'VariableDef({self.type.name}, {self.value!r})'

    def __eq__(self, other) -> bool:
        return isinstance(other, VariableDef) and (self.type, self.value) == (other.type, other.value)

    @staticmethod
    def from_value(value: VariableDefPyTypes) -> 'VariableDef':
        # Must check bool first because bool is derived from int.
        if isinstance(value, bool):
            return VariableDef(ContainerDataType.kBool, value)
        if isinstance(value, int):
            return VariableDef(ContainerDataType.kInt, value)
        if isinstance(value, float):
            return VariableDef(ContainerDataType.kFloat, value)
        if isinstance(value, list) and value and all(isinstance(v, float) for v in value):
            return VariableDef(ContainerDataType.kFloatArray, value)
        if isinstance(value, list) and value and all(isinstance(v, int) and not isinstance(v, bool) for v in value):
            return VariableDef(ContainerDataType.kIntArray, value)
        raise ValueError(f'Cannot infer a variable type for {value!r}')

    @staticmethod
    def _read(stream: ReadStream) -> 'VariableDef':
        value_offset = stream.tell()
        stream.skip(8)
        num = stream.read_u16()
        type = ContainerDataType(stream.read_u8())
        stream.skip(5) # Padding
        end_offset = stream.tell()
        stream.seek(value_offset)

        value: VariableDefPyTypes
        if type == ContainerDataType.kFloat:
            value = stream.read_f32()
        elif type == ContainerDataType.kBool:
            value = stream.read_s32() != 0
        elif type == ContainerDataType.kInt:
            value = stream.read_s32()
        elif type in _ARRAY_VARIABLE_TYPES:
            with SeekContext(stream, stream.read_u64()):
                if type == ContainerDataType.kIntArray:
                    value = [stream.read_s32() for i in range(num)]
                else:
                    value = [stream.read_f32() for i in range(num)]
        else:
            raise ValueError(f'Unsupported variable type: {type!r}')

        if type not in _ARRAY_VARIABLE_TYPES:
            assert num == 1
        stream.seek(end_offset)
        return VariableDef(type, value)

    def _num(self) -> int:
        return len(self.value) if self.type in _ARRAY_VARIABLE_TYPES else 1 # type: ignore

    def _write_value(self, stream: WriteStream) -> typing.Optional[PlaceholderWriter]:
        if self.type == ContainerDataType.kFloat:
            stream.write(f32(self.value)) # type: ignore
            stream.write(u32(0))
        elif self.type in _SCALAR_VARIABLE_TYPES:
            stream.write(s32(int(self.value))) # type: ignore
            stream.write(u32(0))
        else:
            return stream.write_placeholder_ptr()
        return None

    def _write_array(self, stream: WriteStream) -> None:
        for v in self.value: # type: ignore
            stream.write(s32(v) if self.type == ContainerDataType.kIntArray else f32(v))

class EntryPoint(BinaryObject):
    __slots__ = ['name', 'main_event', 'variable_defs', '_sub_flow_event_indices', '_sub_flow_event_indices_offset_writer',
                 '_variable_defs_dic', '_variable_defs_offset_writer']
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.main_event: Index[evfl.event.Event] = Index()
        self.variable_defs: typing.Dict[str, VariableDef] = dict()
        self._sub_flow_event_indices: typing.List[int] = []
        self._sub_flow_event_indices_offset_writer: typing.Optional[PlaceholderWriter] = None
        self._variable_defs_dic: typing.Optional[DicWriter] = None
        self._variable_defs_offset_writer: typing.Optional[PlaceholderWriter] = None

    def _do_read(self, stream: ReadStream) -> None:
        sub_flow_event_indices_offset = stream.read_u64()
        variable_defs_names = stream.read_ptr_object(DicReader)
        variable_defs_offset = stream.read_u64()
        num_sub_flow_event_indices = stream.read_u16()
        num_variable_defs = stream.read_u16()
        self.main_event._idx = stream.read_u16()
        x1e = stream.read_u16()
        assert x1e == 0

        if num_sub_flow_event_indices > 0:
            assert sub_flow_event_indices_offset != 0
            with SeekContext(stream, sub_flow_event_indices_offset):
                self._sub_flow_event_indices = [stream.read_u16() for i in range(num_sub_flow_event_indices)]

        if num_variable_defs > 0:
            assert variable_defs_names is not None and len(variable_defs_names.items) == num_variable_defs
            assert variable_defs_offset != 0
            with SeekContext(stream, variable_defs_offset):
                for name in variable_defs_names.items:
                    self.variable_defs[name] = VariableDef._read(stream)

    def _do_write(self, stream: WriteStream) -> None:
        self._sub_flow_event_indices_offset_writer = stream.write_placeholder_ptr_if(bool(self._sub_flow_event_indices), register=True)
        if self.variable_defs:
            self._variable_defs_dic = DicWriter()
            self._variable_defs_dic.write_placeholder_offset(stream)
            self._variable_defs_offset_writer = stream.write_placeholder_ptr()
        else:
            self._variable_defs_dic = None
            self._variable_defs_offset_writer = None
            stream.write(u64(0))
            stream.write_nullptr(register=True)
        stream.write(u16(len(self._sub_flow_event_indices)))
        stream.write(u16(len(self.variable_defs)))
        stream.write(u16(self.main_event._idx))
        stream.write(u16(0)) # x1e

    def write_extra_data(self, stream: WriteStream) -> None:
        if self._sub_flow_event_indices_offset_writer:
            self._sub_flow_event_indices_offset_writer.write_current_offset(stream)
            for idx in self._sub_flow_event_indices:
                stream.write(u16(idx))
            stream.align(8)

        if self._variable_defs_dic and self._variable_defs_offset_writer:
            for name in self.variable_defs.keys():
                self._variable_defs_dic.insert(name)
            self._variable_defs_dic.write(stream)

            self._variable_defs_offset_writer.write_current_offset(stream)
            array_ptr_writers: typing.List[typing.Tuple[PlaceholderWriter, VariableDef]] = []
            for variable_def in self.variable_defs.values():
                array_ptr_writer = variable_def._write_value(stream)
                if array_ptr_writer:
                    array_ptr_writers.append((array_ptr_writer, variable_def))
                stream.write(u16(variable_def._num()))
                stream.write(u8(variable_def.type))
                stream.write(bytes(5)) # Padding

            # No known file has array variables, so the placement of their values is a guess.
            for array_ptr_writer, variable_def in array_ptr_writers:
                stream.align(8)
                array_ptr_writer.write_current_offset(stream)
                variable_def._write_array(stream)
            stream.align(8)
        else:
            # Nintendo's writer leaves room for an empty variable name DIC even though nothing points to it.
            stream.skip(0x18)
