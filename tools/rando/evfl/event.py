import abc
import evfl.actor
from evfl.common import StringHolder
from evfl.container import Container
from evfl.enums import EventType, Version
from evfl.util import *

def _should_write_params(params: typing.Optional[Container]) -> bool:
    return bool(params and params.data)

def _read_cases(stream: ReadStream, cases_offset: int, num_cases: int) -> typing.Dict[int, RequiredIndex['Event']]:
    cases: typing.Dict[int, RequiredIndex[Event]] = dict()
    with SeekContext(stream, cases_offset):
        for i in range(num_cases):
            value = stream.read_u32()
            event_idx = stream.read_u16()
            cases[value] = RequiredIndex(event_idx)
            stream.align(8)
    return cases

def _write_cases(stream: WriteStream, cases_offset_writer: PlaceholderWriter, cases: typing.Dict[int, RequiredIndex['Event']]) -> None:
    stream.align(8)
    cases_offset_writer.write_current_offset(stream)
    for value, event in cases.items():
        stream.write(u32(value))
        stream.write(u16(event._idx))
        stream.align(8)

class BaseEvent(metaclass=abc.ABCMeta):
    __slots__ = [] # type: ignore

    @abc.abstractmethod
    def _read(self, stream: ReadStream) -> None:
        pass

    @abc.abstractmethod
    def _write(self, stream: WriteStream) -> None:
        pass

    @abc.abstractmethod
    def _write_extra_data(self, stream: WriteStream) -> None:
        pass

class ActionEvent(BaseEvent):
    __slots__ = ['nxt', 'actor', 'actor_action', 'params', '_params_offset_writer']
    def __init__(self) -> None:
        self.nxt: Index[Event] = Index()
        self.actor: RequiredIndex[evfl.actor.Actor] = RequiredIndex()
        self.actor_action: RequiredIndex[StringHolder] = RequiredIndex()
        self.params: typing.Optional[Container] = None
        self._params_offset_writer: typing.Optional[PlaceholderWriter] = None

    def _read(self, stream: ReadStream) -> None:
        self.nxt._idx = stream.read_u16()
        self.actor._idx = stream.read_u16()
        self.actor_action._idx = stream.read_u16()
        self.params = stream.read_ptr_object(Container)
        unused_ptr_1 = stream.read_u64()
        unused_ptr_2 = stream.read_u64()
        assert unused_ptr_1 == 0 and unused_ptr_2 == 0

    def _write(self, stream: WriteStream) -> None:
        stream.write(u16(self.nxt._idx))
        stream.write(u16(self.actor._idx))
        stream.write(u16(self.actor_action._idx))
        self._params_offset_writer = stream.write_placeholder_ptr_if(_should_write_params(self.params))
        stream.write(u64(0))
        stream.write(u64(0))

    def _write_extra_data(self, stream: WriteStream) -> None:
        if self._params_offset_writer and self.params:
            self._params_offset_writer.write_current_offset(stream)
            self.params.write(stream)

class SwitchEvent(BaseEvent):
    __slots__ = ['actor', 'actor_query', 'params', 'cases', '_params_offset_writer', '_cases_offset_writer']
    def __init__(self) -> None:
        self.actor: RequiredIndex[evfl.actor.Actor] = RequiredIndex()
        self.actor_query: RequiredIndex[StringHolder] = RequiredIndex()
        self.params: typing.Optional[Container] = None
        self.cases: typing.Dict[int, RequiredIndex[Event]] = dict()
        self._params_offset_writer: typing.Optional[PlaceholderWriter] = None
        self._cases_offset_writer: typing.Optional[PlaceholderWriter] = None

    def _read(self, stream: ReadStream) -> None:
        num_cases = stream.read_u16() # can be zero.
        self.actor._idx = stream.read_u16()
        self.actor_query._idx = stream.read_u16()
        self.params = stream.read_ptr_object(Container)
        self.cases = _read_cases(stream, stream.read_u64(), num_cases)
        unused_ptr = stream.read_u64()
        assert unused_ptr == 0

    def _write(self, stream: WriteStream) -> None:
        stream.write(u16(len(self.cases))) # can be zero.
        stream.write(u16(self.actor._idx))
        stream.write(u16(self.actor_query._idx))
        self._params_offset_writer = stream.write_placeholder_ptr_if(_should_write_params(self.params))
        self._cases_offset_writer = stream.write_placeholder_ptr_if(bool(self.cases), register=True)
        stream.write(u64(0))

    def _write_extra_data(self, stream: WriteStream) -> None:
        # Nintendo's software writes the switch case struct first.
        if self._cases_offset_writer:
            _write_cases(stream, self._cases_offset_writer, self.cases)

        if self._params_offset_writer and self.params:
            self._params_offset_writer.write_current_offset(stream)
            self.params.write(stream)

class ForkEvent(BaseEvent):
    __slots__ = ['join', 'forks', '_forks_offset_writer']
    def __init__(self) -> None:
        self.join: RequiredIndex[Event] = RequiredIndex()
        self.forks: typing.List[RequiredIndex[Event]] = []
        self._forks_offset_writer: typing.Optional[PlaceholderWriter] = None

    def _read(self, stream: ReadStream) -> None:
        num_forks = stream.read_u16()
        self.join._idx = stream.read_u16()
        unused = stream.read_u16()
        assert unused == 0
        forks_offset = stream.read_u64()
        if num_forks == 0 or forks_offset == 0:
            raise ValueError('Fork event should have forks')
        with SeekContext(stream, forks_offset):
            self.forks = [RequiredIndex(stream.read_u16()) for i in range(num_forks)]
        unused_ptr_1 = stream.read_u64()
        unused_ptr_2 = stream.read_u64()
        assert unused_ptr_1 == 0 and unused_ptr_2 == 0

    def _write(self, stream: WriteStream) -> None:
        assert self.forks
        stream.write(u16(len(self.forks)))
        stream.write(u16(self.join._idx))
        stream.write(u16(0)) # Unused
        self._forks_offset_writer = stream.write_placeholder_ptr()
        stream.write(u64(0))
        stream.write(u64(0))

    def _write_extra_data(self, stream: WriteStream) -> None:
        if self._forks_offset_writer:
            self._forks_offset_writer.write_current_offset(stream)
            for fork in self.forks:
                stream.write(u16(fork._idx))
            stream.align(8)

class JoinEvent(BaseEvent):
    __slots__ = ['nxt']
    def __init__(self) -> None:
        self.nxt: Index[Event] = Index()

    def _read(self, stream: ReadStream) -> None:
        self.nxt._idx = stream.read_u16()
        unused_xc = stream.read_u16()
        unused_xe = stream.read_u16()
        assert unused_xc == 0 and unused_xe == 0
        unused_params = stream.read_u64()
        unused_ptr_1 = stream.read_u64()
        unused_ptr_2 = stream.read_u64()
        assert unused_params == 0 and unused_ptr_1 == 0 and unused_ptr_2 == 0

    def _write(self, stream: WriteStream) -> None:
        stream.write(u16(self.nxt._idx))
        stream.write(u16(0))
        stream.write(u16(0))
        stream.write(u64(0))
        stream.write(u64(0))
        stream.write(u64(0))

    def _write_extra_data(self, stream: WriteStream) -> None:
        return

class SubFlowEvent(BaseEvent):
    __slots__ = ['nxt', 'params', 'res_flowchart_name', 'entry_point_name', '_params_offset_writer']
    def __init__(self) -> None:
        self.nxt: Index[Event] = Index()
        self.params: typing.Optional[Container] = None
        self.res_flowchart_name = ''
        self.entry_point_name = ''
        self._params_offset_writer: typing.Optional[PlaceholderWriter] = None

    def _read(self, stream: ReadStream) -> None:
        self.nxt._idx = stream.read_u16()
        unused_xc = stream.read_u16()
        unused_xe = stream.read_u16()
        assert unused_xc == 0 and unused_xe == 0
        self.params = stream.read_ptr_object(Container)
        self.res_flowchart_name = stream.read_string_ref()
        self.entry_point_name = stream.read_string_ref()
        assert self.entry_point_name

    def _write(self, stream: WriteStream) -> None:
        stream.write(u16(self.nxt._idx))
        stream.write(u16(0)) # Unused
        stream.write(u16(0)) # Unused
        self._params_offset_writer = stream.write_placeholder_ptr_if(_should_write_params(self.params))
        assert self.entry_point_name
        stream.write_string_ref(self.res_flowchart_name)
        stream.write_string_ref(self.entry_point_name)

    def _write_extra_data(self, stream: WriteStream) -> None:
        if self._params_offset_writer and self.params:
            self._params_offset_writer.write_current_offset(stream)
            self.params.write(stream)

class SubFlowSwitchEvent(BaseEvent):
    __slots__ = ['params', 'cases', 'res_flowchart_name', 'entry_point_name', '_params_offset_writer', '_cases_offset_writer']
    def __init__(self) -> None:
        self.params: typing.Optional[Container] = None
        self.cases: typing.Dict[int, RequiredIndex[Event]] = dict()
        self.res_flowchart_name = ''
        self.entry_point_name = ''
        self._params_offset_writer: typing.Optional[PlaceholderWriter] = None
        self._cases_offset_writer: typing.Optional[PlaceholderWriter] = None

    def _read(self, stream: ReadStream) -> None:
        num_cases = stream.read_u16()
        unused_xc = stream.read_u16()
        unused_xe = stream.read_u16()
        assert unused_xc == 0 and unused_xe == 0
        self.params = stream.read_ptr_object(Container)
        self.cases = _read_cases(stream, stream.read_u64(), num_cases)
        self.res_flowchart_name = stream.read_string_ref()
        self.entry_point_name = stream.read_string_ref()
        assert self.entry_point_name

    def _write(self, stream: WriteStream) -> None:
        stream.write(u16(len(self.cases)))
        stream.write(u16(0)) # Unused
        stream.write(u16(0)) # Unused
        self._params_offset_writer = stream.write_placeholder_ptr_if(_should_write_params(self.params))
        self._cases_offset_writer = stream.write_placeholder_ptr_if(bool(self.cases), register=True)
        assert self.entry_point_name
        stream.write_string_ref(self.res_flowchart_name)
        stream.write_string_ref(self.entry_point_name)

    def _write_extra_data(self, stream: WriteStream) -> None:
        if self._cases_offset_writer:
            _write_cases(stream, self._cases_offset_writer, self.cases)

        if self._params_offset_writer and self.params:
            self._params_offset_writer.write_current_offset(stream)
            self.params.write(stream)

class ReturnEvent(BaseEvent):
    __slots__ = ['value']
    def __init__(self, value: int = 0) -> None:
        self.value = value

    def _read(self, stream: ReadStream) -> None:
        unused_xa = stream.read_u16()
        self.value = stream.read_u32()
        unused = stream.read(0x18)
        assert unused_xa == 0 and not any(unused)

    def _write(self, stream: WriteStream) -> None:
        stream.write(u16(0))
        stream.write(u32(self.value))
        stream.write(bytes(0x18))

    def _write_extra_data(self, stream: WriteStream) -> None:
        return

_EVENT_TYPES: typing.Dict[EventType, typing.Type[BaseEvent]] = {
    EventType.kAction: ActionEvent,
    EventType.kSwitch: SwitchEvent,
    EventType.kFork: ForkEvent,
    EventType.kJoin: JoinEvent,
    EventType.kSubFlow: SubFlowEvent,
    EventType.kSubFlowSwitch: SubFlowSwitchEvent,
    EventType.kReturn: ReturnEvent,
}

_VERSION_4_EVENT_TYPES = (EventType.kSubFlowSwitch, EventType.kReturn)

def _get_event_size(version: Version) -> int:
    return 0x30 if version >= Version.V4 else 0x28

class Event(BinaryObject):
    __slots__ = ['name', 'data']
    def __init__(self) -> None:
        super().__init__()
        self.name = ''
        self.data: BaseEvent

    def _do_read(self, stream: ReadStream) -> None:
        start_offset = stream.tell()
        self.name = stream.read_string_ref()
        etype = stream.read_u8()
        if etype not in _EVENT_TYPES:
            raise ValueError(f'Unknown event type: {etype}')
        if etype in _VERSION_4_EVENT_TYPES:
            require_version(stream, Version.V4, _EVENT_TYPES[EventType(etype)].__name__)
        self.data = _EVENT_TYPES[EventType(etype)]()
        stream.skip(1)
        self.data._read(stream)

        unused = stream.read(start_offset + _get_event_size(stream.version) - stream.tell())
        assert not any(unused)

    def _do_write(self, stream: WriteStream) -> None:
        start_offset = stream.tell()
        etype = next((t for t, data_type in _EVENT_TYPES.items() if isinstance(self.data, data_type)), None)
        if etype is None:
            raise TypeError(f'Unknown event data type: {type(self.data).__name__}')
        if etype in _VERSION_4_EVENT_TYPES:
            require_version(stream, Version.V4, type(self.data).__name__)

        stream.write_string_ref(self.name)
        stream.write(u8(etype))
        stream.write(u8(0)) # Padding
        self.data._write(stream)
        stream.write(bytes(start_offset + _get_event_size(stream.version) - stream.tell()))

    def write_extra_data(self, stream: WriteStream) -> None:
        self.data._write_extra_data(stream)
